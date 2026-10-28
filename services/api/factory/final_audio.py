"""The revision-bound final mix shared by preview, Blender and portable export."""
import hashlib
import json
from pathlib import Path

from .config import settings
from .render import ffmpeg, probe
from .security import digest, run, safe_path


def register(project, path, provenance):
    path = Path(path).resolve()
    root_name = next((name for name in ('storage_root', 'output_dir')
                      if path.is_relative_to(getattr(settings, name).resolve())), None)
    if not root_name:
        raise ValueError('Final audio must be inside application storage')
    data = probe(path)
    stream = next((s for s in data['streams'] if s['codec_type'] == 'audio'), {})
    if stream.get('codec_name') != 'pcm_s16le':
        raise ValueError('Final mix must be PCM16 WAV')
    duration = float(data['format']['duration'])
    if abs(duration-project.target_duration) > 1/project.fps:
        raise ValueError('Audio duration conflicts with project duration; edit the timeline or duration explicitly')
    reference = dict(revision=project.revision, root=root_name,
                     path=path.relative_to(getattr(settings, root_name).resolve()).as_posix(),
                     sha256=digest(path), duration=duration, provenance=provenance)
    if getattr(project, 'music_plan', None):
        reference['plan_sha256'] = hashlib.sha256(json.dumps(project.music_plan, sort_keys=True).encode()).hexdigest()
    project.narration = {**project.narration, 'final': reference}
    return path


def resolve(project, job=None):
    reference = project.narration.get('final')
    if reference:
        if reference['revision'] != project.revision:
            raise ValueError('Final mix belongs to another revision; validate a new mix')
        if reference.get('plan_sha256') and reference['plan_sha256'] != hashlib.sha256(
                json.dumps(project.music_plan, sort_keys=True).encode()).hexdigest():
            raise ValueError('Music plan changed; validate the final mix again')
        if reference['root'] not in {'storage_root', 'output_dir'}:
            raise ValueError('Invalid final audio storage')
        path = safe_path(getattr(settings, reference['root']), reference['path'])
        if not path.is_file() or digest(path) != reference['sha256']:
            raise ValueError('Final mix missing or changed; validate the mix again')
        return path
    if getattr(project, 'music_plan', None):
        raise ValueError('Finish and validate the Music Studio mix before storyboarding or rendering')
    # Legacy adoption: an explicit import always wins over old generated/checkpoint audio.
    candidate = (safe_path(settings.storage_root, project.narration['path'])
                 if project.narration.get('path') else
                 (job.checkpoint.get('audio') if job and job.revision == project.revision else None)
                 or project.narration.get('generated_path'))
    if not candidate:
        raise ValueError('Prepare measured audio before rendering')
    path = Path(candidate).resolve()
    if not any(path.is_relative_to(root.resolve()) for root in (settings.storage_root, settings.output_dir)):
        raise ValueError('Invalid audio path')
    if not path.is_file() or path.stat().st_size > 200*1024**2:
        raise ValueError('Audio missing or exceeds the 200 MiB audio limit')
    if next((s for s in probe(path)['streams'] if s['codec_type'] == 'audio'), {}).get('codec_name') != 'pcm_s16le':
        destination = settings.storage_root/'final-audio'/project.id/f'{project.revision}.wav'
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix('.partial.wav')
        run([ffmpeg(), '-v', 'error', '-y', '-i', path, '-vn', '-ar', '24000', '-ac', '1',
             '-c:a', 'pcm_s16le', temporary], timeout=300)
        temporary.replace(destination)
        path = destination
    return register(project, path, {'source': 'import' if project.narration.get('path') else 'legacy-production'})
