"""Local export registry and return validation. Never sends credentials externally."""
import json
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from content_factory_render.archive import atomic_json, identity, pack, sha, source_sha, unpack
from content_factory_render.contract import InputPackage, Profile, ResultPackage
from content_factory_render.runner import valid_frame
from fastapi import HTTPException
from sqlalchemy import select, text

from .api_helpers import no_running_job, project_or_404
from .config import ROOT, settings
from .db import Session
from .models import ExternalRenderExport, ProductionJob, RenderArtifact, utcnow
from .queue import enqueue
from .render import ffprobe, probe, validate_video

# Updated to an immutable reviewed render-only commit when the release is committed.
from .render_release import RENDER_COMMIT
from .visual_schema import VisualBoard, VisualSettings

TEMPLATE = ROOT/'templates/blender/factory_scene.py'
NOTEBOOK_URL = 'https://colab.research.google.com/github/mrJoao28/Content-Factory/blob/b294cd057fc826ee5eb02044b9ab3bbd196985ab/notebooks/content_factory_colab.ipynb'


def current_job(db, project):
    return db.scalar(select(ProductionJob).where(ProductionJob.project_id == project.id,
                                                ProductionJob.revision == project.revision))


def prepared(project, job):
    """Read only declared scene data and a measured local audio file, no AI invocation."""
    visual = VisualSettings.model_validate(project.visual_config)
    if visual.engine != 'blender_3d':
        raise ValueError('External rendering requires a Blender 3D project')
    board = VisualBoard.model_validate(project.storyboard).validate_project(project.target_duration, project.fps)
    from .final_audio import resolve
    candidate = resolve(project, job)
    if not candidate:
        raise ValueError('Prepare storyboard and measured narration before exporting')
    audio = Path(candidate).resolve()
    roots = (settings.output_dir.resolve(), settings.storage_root.resolve())
    if not any(audio.is_relative_to(root) for root in roots) or not audio.is_file() or audio.stat().st_size > 200*1024**2:
        raise ValueError('Prepared audio must be an existing bounded file inside application storage')
    data = probe(audio)
    stream = next((s for s in data['streams'] if s['codec_type'] == 'audio'), {})
    if stream.get('codec_name') != 'pcm_s16le' or abs(float(data['format']['duration'])-board.duration) > 1/project.fps:
        raise ValueError('Portable narration requires measured PCM16 WAV matching the storyboard; prepare audio first')
    return visual, board, audio


def location(project_id, revision, target, hardware):
    with Session.begin() as db:
        db.execute(text('BEGIN IMMEDIATE'))
        project = project_or_404(db, project_id)
        no_running_job(db, project_id)
        if project.revision != revision:
            raise HTTPException(409, 'Revision changed; refresh before changing execution location')
        visual = VisualSettings.model_validate(project.visual_config)
        if visual.engine != 'blender_3d':
            raise ValueError('Choose Blender 3D before selecting Colab execution')
        job = current_job(db, project)
        if job and job.owner and job.state not in {'PAUSED', 'CANCELLED', 'WAITING_FOR_EXTERNAL_RENDER'}:
            raise HTTPException(409, 'Pause the active production explicitly and wait for its render lease to release before transferring it')
        if job and job.state in {'SCHEDULED', 'PUBLISHED', 'DRIVE_UPLOAD', 'PUBLICATION_PREPARATION'}:
            raise HTTPException(409, 'Stop publication work before changing render execution')
        # A different hardware choice creates a new registered export; previous IDs are invalidated.
        if target != visual.execution_location or hardware != visual.external_hardware:
            for row in db.scalars(select(ExternalRenderExport).where(ExternalRenderExport.project_id == project.id,
                                                                     ExternalRenderExport.state == 'EXPORTED')):
                row.state = 'SUPERSEDED'
        project.visual_config = {**visual.model_dump(mode='json'), 'execution_location': target,
                                 'external_hardware': hardware}
        if not job:
            job = enqueue(db, project)
        try:
            prepared(project, job)
            ready = True
        except ValueError:
            ready = False
        if ready:
            job.checkpoint = {**job.checkpoint, "_render_prepared": True}
        job.state = 'WAITING_FOR_EXTERNAL_RENDER' if target == 'colab' and ready else 'DRAFT'
        job.owner, job.lease_until, job.error = None, None, None
        job.available_at = utcnow()
        job.checkpoint = {k: v for k, v in job.checkpoint.items() if k != '_failure'}
        project.status = job.state
        return {'state': job.state, 'execution_location': target, 'checkpoints_preserved': True,
                'notebook_url': NOTEBOOK_URL}


def export_project(project_id, revision):
    with Session.begin() as db:
        db.execute(text('BEGIN IMMEDIATE'))
        project = project_or_404(db, project_id)
        no_running_job(db, project_id)
        if project.revision != revision:
            raise HTTPException(409, 'Revision changed')
        job = current_job(db, project)
        if not job or job.state != 'WAITING_FOR_EXTERNAL_RENDER':
            raise HTTPException(409, 'Choose Prepare for Colab and wait for storyboard/audio preparation first')
        visual, board, audio = prepared(project, job)
        profile = Profile(quality=visual.quality, width=project.width, height=project.height, fps=project.fps,
                          samples=8 if visual.quality == 'preview' else 32, hardware=visual.external_hardware)
        export_id = str(uuid4())
        package = InputPackage(export_id=export_id, project_id=project.id, revision=project.revision,
                               render_commit=RENDER_COMMIT, template_sha256=source_sha(TEMPLATE), board=board,
                               profile=profile, audio={'sha256': sha(audio), 'size': audio.stat().st_size})
        payload = package.model_dump(mode='json')
        semantic = identity({k: v for k, v in payload.items() if k != 'export_id'})
        old = db.scalar(select(ExternalRenderExport).where(ExternalRenderExport.semantic_hash == semantic,
                                                          ExternalRenderExport.state == 'EXPORTED').limit(1))
        if old:
            return {'export_id': old.id, 'download_url': f'/external-render/exports/{old.id}/download',
                    'notebook_url': NOTEBOOK_URL, 'input_hash': identity(old.manifest)}
        folder = settings.output_dir/'external-exports'
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder/f'{export_id}.zip'
        with tempfile.TemporaryDirectory(dir=folder) as temp:
            manifest = Path(temp)/'manifest.json'
            atomic_json(manifest, payload)
            pack(destination, {'manifest.json': manifest, 'audio/narration.wav': audio})
        db.add(ExternalRenderExport(id=export_id, project_id=project.id, revision=project.revision,
                                   semantic_hash=semantic, manifest=payload,
                                   path=str(destination.relative_to(settings.output_dir))))
        return {'export_id': export_id, 'download_url': f'/external-render/exports/{export_id}/download',
                'notebook_url': NOTEBOOK_URL, 'input_hash': identity(payload)}


def check_registered(db, project_id, result):
    project = project_or_404(db, project_id)
    no_running_job(db, project_id)
    row = db.get(ExternalRenderExport, str(result.export_id))
    job = current_job(db, project)
    if (not row or row.project_id != project.id or str(result.project_id) != project.id
            or row.revision != project.revision or result.revision != project.revision
            or row.state not in {'EXPORTED', 'IMPORTED'} or not job
            or job.state not in {'WAITING_FOR_EXTERNAL_RENDER', 'HUMAN_REVIEW', 'APPROVED'}):
        raise HTTPException(409, 'Unknown, stale, cancelled or superseded external export')
    package = InputPackage.model_validate(row.manifest)
    if result.input_hash != identity(row.manifest) or result.profile != package.profile:
        raise HTTPException(409, 'Return input hash/profile differs from the registered export; change profile locally and reexport explicitly')
    _, board, audio = prepared(project, job)
    if (board != package.board or sha(audio) != package.audio.sha256
            or (project.width, project.height, project.fps) != (package.profile.width, package.profile.height, package.profile.fps)):
        raise HTTPException(409, 'Prepared inputs changed after export; create a new export')
    return project, job, row, package


def import_result(project_id, archive):
    with tempfile.TemporaryDirectory(dir=settings.output_dir) as temp:
        names = unpack(archive, temp, allowed={'result.json', 'video.mp4', 'thumbnail.png', 'report.json'})
        if names != {'result.json', 'video.mp4', 'thumbnail.png', 'report.json'}:
            raise ValueError('Return package files missing')
        folder = Path(temp)
        if (folder/'result.json').stat().st_size > 65536 or (folder/'report.json').stat().st_size > 65536:
            raise ValueError('Return metadata exceeds limits')
        result = ResultPackage.model_validate_json((folder/'result.json').read_bytes())
        for name, entry in result.files.items():
            path = folder/name
            if path.stat().st_size != entry.size or sha(path) != entry.sha256:
                raise ValueError('Return file integrity mismatch')
        with Session() as db:
            _, _, _, package = check_registered(db, project_id, result)
        p = package.profile
        movie = folder/'video.mp4'
        validation = validate_video(movie, p.width, p.height, p.fps, package.board.duration)
        video = next(x for x in validation['media']['streams'] if x['codec_type'] == 'video')
        from .security import run
        counted = json.loads(run([ffprobe(), '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                                  '-show_entries', 'stream=nb_read_frames', '-of', 'json', movie], timeout=1800))
        expected = round(package.board.duration*p.fps)
        if int(video.get('nb_frames', -1)) != expected or int(counted['streams'][0].get('nb_read_frames', -1)) != expected:
            raise ValueError('Returned video frame count differs from the exported timeline')
        audio_stream = next(x for x in validation['media']['streams'] if x['codec_type'] == 'audio')
        if (abs(float(video.get('duration', 0))-package.board.duration) > 1/p.fps
                or abs(float(audio_stream.get('duration', 0))-package.board.duration) > .1
                or abs(float(audio_stream.get('start_time', 0))) > .1):
            raise ValueError('Returned video/audio timing differs from the exported timeline')
        validation['checks'].update(frame_count=True, audio_timeline=True)
        if not valid_frame(folder/'thumbnail.png', p.width, p.height):
            raise ValueError('Thumbnail dimensions/PNG invalid')
        # Use a thumbnail extracted locally from the verified video, never trust an arbitrary supplied picture.
        from .render import ffmpeg
        run([ffmpeg(), '-v', 'error', '-y', '-i', movie, '-frames:v', '1', folder/'verified.png'], timeout=60)
        (folder/'verified.png').replace(folder/'thumbnail.png')
        movie_hash = sha(movie)
        validation['visual'] = {'engine': 'blender_3d', 'origin': 'Colab assisted',
                                'export_id': str(result.export_id), 'profile': p.model_dump(),
                                'effective_backend': result.effective_backend, 'execution_hash': result.execution_hash,
                                'provenance': 'reported by notebook; media verified locally'}
        with Session.begin() as db:
            db.execute(text('BEGIN IMMEDIATE'))
            project, job, row, _ = check_registered(db, project_id, result)
            if row.state == 'IMPORTED':
                if row.artifact_hash != movie_hash:
                    raise HTTPException(409, 'This export already has a different imported result')
                return {'state': project.status, 'sha256': movie_hash, 'duplicate': True}
            destination = settings.output_dir/project.id/str(project.revision)/'external'/row.id
            destination.parent.mkdir(parents=True, exist_ok=True)
            recovered = destination.exists()
            if recovered and (not (destination/'video.mp4').is_file() or sha(destination/'video.mp4') != movie_hash
                              or not (destination/'result.json').is_file()
                              or sha(destination/'result.json') != sha(folder/'result.json')):
                raise HTTPException(409, 'Interrupted import conflicts with this result; preserved for inspection')
            # Stage the complete artifact on the same filesystem, then rename atomically.
            if not recovered:
                stage = destination.with_name(row.id+'.partial-'+str(uuid4()))
                stage.mkdir()
                for name in ('video.mp4', 'thumbnail.png', 'report.json', 'result.json'):
                    shutil.copyfile(folder/name, stage/name)
                atomic_json(stage/'script.json', project.script)
                atomic_json(stage/'metadata.json', project.metadata_json)
                def stamp(seconds):
                    ms = round(seconds*1000)
                    return f'{ms//3600000:02}:{ms//60000 % 60:02}:{ms//1000 % 60:02},{ms % 1000:03}'
                captions, start = [], 0
                for index, scene in enumerate(package.board.scenes, 1):
                    captions.append(f'{index}\n{stamp(start)} --> {stamp(start+scene.duration)}\n{scene.narration}\n')
                    start += scene.duration
                (stage/'captions.srt').write_text('\n'.join(captions), encoding='utf-8')
                stage.replace(destination)
            db.add(RenderArtifact(project_id=project.id, revision=project.revision,
                                  path=str((destination/'video.mp4').relative_to(settings.output_dir)),
                                  sha256=movie_hash, probe=validation, render_seconds=0))
            row.state, row.artifact_hash = 'IMPORTED', movie_hash
            project.approved_hash, project.status = None, 'HUMAN_REVIEW'
            job.state, job.owner, job.lease_until, job.error = 'HUMAN_REVIEW', None, None, None
            job.checkpoint = {**{k: v for k, v in job.checkpoint.items() if k != '_failure'},
                              '_external_render': {'export_id': row.id, 'sha256': movie_hash}}
        return {'state': 'HUMAN_REVIEW', 'sha256': movie_hash, 'duplicate': False}
