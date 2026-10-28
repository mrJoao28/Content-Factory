"""Compile exact reviewed 3D video units with FFmpeg, no invented footage or trimming."""
import time

from sqlalchemy import select

from .config import settings
from .db import Session
from .models import ProductionJob, RenderArtifact, VideoProject
from .music_schema import MusicPlan
from .render import ffmpeg, probe, validate_video
from .security import Cancelled, digest, safe_path


def sources(db, project):
    plan = MusicPlan.model_validate(project.music_plan).validate_duration(project.target_duration)
    result = []
    for segment in plan.segments:
        source = db.get(VideoProject, segment.source_project_id)
        artifact = db.scalar(select(RenderArtifact).where(RenderArtifact.project_id == segment.source_project_id,
                           RenderArtifact.sha256 == segment.source_artifact_hash))
        if not source or not artifact or source.approved_hash != artifact.sha256:
            raise ValueError('Compilation requires an approved source video with the selected hash')
        path = safe_path(settings.output_dir, artifact.path)
        if not path.is_file() or digest(path) != artifact.sha256:
            raise ValueError('Compilation source is missing or has changed')
        duration = float(probe(path)['format']['duration'])
        if abs(duration-segment.duration) > 1/project.fps:
            raise ValueError('Compilation segment duration differs from its measured source; edit explicitly')
        if (source.width, source.height, source.fps) != (project.width, project.height, project.fps):
            raise ValueError('Compilation source dimensions and FPS must match; no silent profile conversion')
        result.append((path, artifact.sha256, duration))
    return result


def assemble(job_id, owner, cancel):
    from .music_audio import normalize, process
    from .queue import checkpoint
    checkpoint(job_id, owner, 'RENDERING')
    with Session() as db:
        job = db.get(ProductionJob, job_id)
        project = db.get(VideoProject, job.project_id)
        units = sources(db, project)
        revision, project_id = project.revision, project.id
    folder = settings.output_dir/project_id/str(revision)
    folder.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    # Normalize container timestamps per unit; content is not stretched, cropped or repeated.
    intermediate = []
    for index, (path, hashed, duration) in enumerate(units):
        if cancel():
            raise Cancelled('Compilation cancelled; completed units retained')
        segment = folder/f'{index:03}-{hashed}.mkv'
        if not segment.exists():
            temporary = segment.with_suffix('.partial.mkv')
            process([ffmpeg(), '-v', 'error', '-y', '-i', path, '-map', '0:v:0', '-map', '0:a:0',
                     '-c:v', 'copy', '-af', f'atrim=duration={duration},asetpts=PTS-STARTPTS',
                     '-c:a', 'pcm_s16le', '-ar', '24000', '-ac', 1, '-f', 'matroska', temporary], cancel=cancel)
            temporary.replace(segment)
        intermediate.append(segment)
    movie = folder/'video.mp4'
    temporary = folder/'video.partial.mp4'
    # Decode each original MP4 before concatenating: otherwise AAC priming/padding
    # accumulates at every boundary. Only encoder padding beyond the approved unit's
    # container duration is discarded; unit content/timing is never shortened to fit a plan.
    listing = folder/'units.txt'
    listing.write_text(''.join(f"file '{p.name}'\n" for p in intermediate), encoding='utf-8')
    process([ffmpeg(), '-v', 'error', '-y', '-f', 'concat', '-safe', 1, '-i', listing, '-c:v', 'libx264', '-preset', 'fast',
             '-c:a', 'aac', '-movflags', '+faststart', temporary], cancel=cancel, timeout=1800)
    report = validate_video(temporary, project.width, project.height, project.fps, project.target_duration)
    temporary.replace(movie)
    process([ffmpeg(), '-v', 'error', '-y', '-i', movie, '-frames:v', 1, folder/'thumbnail.png'], cancel=cancel)
    audio = settings.storage_root/'music-mixes'/project_id/str(revision)/'final.wav'
    audio.parent.mkdir(parents=True, exist_ok=True)
    normalize(movie, audio)
    with Session.begin() as db:
        current = db.get(VideoProject, project_id)
        if cancel() or current.revision != revision:
            raise Cancelled('Compilation changed')
        from .final_audio import register
        register(current, audio, {'source': 'reviewed-compilation', 'units': [h for _, h, _ in units]})
        existing = db.scalar(select(RenderArtifact).where(RenderArtifact.project_id == project_id,
                                                           RenderArtifact.revision == revision))
        if not existing:
            report['visual'] = {'engine': 'reviewed-unit-compilation', 'origin': 'local',
                                'sources': [h for _, h, _ in units]}
            db.add(RenderArtifact(project_id=project_id, revision=revision,
                                  path=str(movie.relative_to(settings.output_dir)), sha256=digest(movie),
                                  probe=report, render_seconds=time.monotonic()-started))
    checkpoint(job_id, owner, 'HUMAN_REVIEW')
