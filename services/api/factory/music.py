"""Music workflow runs on the existing leased, cancellable production worker."""
import hashlib
import json
from pathlib import Path

from sqlalchemy import select

from .config import settings
from .db import Session
from .models import ExternalRenderExport, MusicVersion, ProductionJob, VideoProject
from .music_schema import MusicPlan
from .security import Cancelled, ConfigurationRequired, digest, safe_path


class MusicRequired(ConfigurationRequired):
    state = 'WAITING_FOR_MUSIC'
    code = 'music_audio_required'


def supersede_exports(db, project_id):
    for row in db.scalars(select(ExternalRenderExport).where(
            ExternalRenderExport.project_id == project_id, ExternalRenderExport.state == 'EXPORTED')):
        row.state = 'SUPERSEDED'


def signature(segment):
    value = segment.model_dump(exclude={'gain', 'instrumental_gain', 'effects_gain', 'fade_in', 'fade_out', 'ducking', 'beats', 'events', 'mouth_times'})
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def invalidate(db, project, *, storyboard=True):
    """Retain old files/versions and text checkpoints, never reuse incompatible output."""
    from .queue import enqueue
    previous = db.scalar(select(ProductionJob).where(ProductionJob.project_id == project.id,
                                                   ProductionJob.revision == project.revision))
    saved = {k: v for k, v in (previous.checkpoint if previous else {}).items()
             if k in {'creative_director', 'script_writer', '_ai_selection', '_ai_step_sources', '_music_boards'}}
    if project.music_plan:
        db.add(MusicVersion(project_id=project.id, revision=project.revision,
                            content=project.music_plan, takes=project.music_state))
    for job in db.scalars(select(ProductionJob).where(ProductionJob.project_id == project.id)):
        if job.revision == project.revision and job.state not in {'PUBLISHED', 'APPROVED', 'HUMAN_REVIEW', 'SCHEDULED'}:
            job.state = 'CANCELLED'
    supersede_exports(db, project.id)
    project.revision += 1
    project.approved_hash = None
    project.narration = {}
    if storyboard:
        project.storyboard = {}
    project.status = 'WAITING_FOR_MUSIC'
    db.flush()
    job = enqueue(db, project)
    job.checkpoint = {**job.checkpoint, **saved}
    job.state = 'WAITING_FOR_MUSIC'
    return job


def save_plan(db, project, plan):
    plan.validate_duration(project.target_duration)
    from .visual_schema import catalog
    available = catalog()
    if project.visual_config.get('engine') != 'blender_3d':
        raise ValueError('Music animation currently requires the explicit Blender 3D engine')
    if any(c not in available['characters'] for c in plan.characters) or plan.environment not in available['environments']:
        raise ValueError('Choose characters and an environment available in the render catalog')
    for segment in plan.segments:
        if abs(segment.duration*project.fps-round(segment.duration*project.fps)) > .000001:
            raise ValueError('Each planned music segment must represent whole frames; edit durations explicitly')
        if any(e.character_id not in plan.characters for e in segment.events):
            raise ValueError('Music events reference a character outside this production')
        if segment.character_id and segment.character_id not in plan.characters:
            raise ValueError('Singer is not in the cast')
    if project.music_plan == plan.model_dump(mode='json'):
        return
    old = project.music_plan
    def visual_content(value):
        result = dict(value)
        result['segments'] = [{k: v for k, v in s.items() if k not in {
            'gain', 'instrumental_gain', 'effects_gain', 'fade_in', 'fade_out', 'ducking'}}
            for s in value.get('segments', [])]
        return result
    invalidate(db, project, storyboard=visual_content(old) != visual_content(plan.model_dump(mode='json')))
    project.music_plan = plan.model_dump(mode='json')
    takes = project.music_state.get('takes', {})
    project.music_state = {**project.music_state, 'editorial_format': plan.format, 'takes': {
        s.id: {role: take for role, take in takes.get(s.id, {}).items() if take['signature'] == signature(s)}
        for s in plan.segments}}


def take_path(take):
    path = safe_path(settings.storage_root, take['path'])
    if not path.is_file() or digest(path) != take['sha256']:
        raise ValueError('Music take missing or changed; select or import another take')
    return path


def timeline(project):
    if not project.music_plan:
        return []
    plan = MusicPlan.model_validate(project.music_plan)
    takes = project.music_state.get('takes', {})
    result, start, measured_start = [], 0.0, 0.0
    for segment in plan.segments:
        selected = takes.get(segment.id, {})
        measured = max((t['duration'] for t in selected.values()), default=0) if segment.kind != 'pause' else segment.duration
        ready = segment.kind == 'pause' or bool(selected)
        if segment.kind == 'instrumental':
            ready = 'instrumental' in selected or 'premixed' in selected
        if segment.kind == 'song':
            ready = 'premixed' in selected or 'vocals' in selected
        if segment.kind in {'narration', 'dialogue'}:
            ready = 'speech' in selected
        conflict = not ready or abs(measured-segment.duration) > 1/project.fps or any(
            abs(t['duration']-segment.duration) > 1/project.fps
            for role, t in selected.items() if role != 'effects')
        measured_end = measured_start+measured if measured_start is not None and ready else None
        result.append(dict(id=segment.id, start=start, end=start+segment.duration,
                           planned=segment.duration, measured=measured, conflict=conflict,
                           measured_start=measured_start if ready else None, measured_end=measured_end,
                           state='audio_required' if not ready else 'duration_conflict' if conflict else 'ready',
                           beats=[{**b.model_dump(), 'global_time': start+b.time} for b in segment.beats]))
        start += segment.duration
        measured_start = measured_end
    return result


def store_take(db, project, segment, path, role, provenance):
    from uuid import uuid4

    from .music_audio import normalize
    from .render import probe
    directory = settings.storage_root/'music'/project.id
    if float(probe(path)['format']['duration']) > 600:
        raise ValueError('Each take is limited to 600 seconds; split long material explicitly')
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory/(uuid4().hex+'.wav')
    normalize(path, destination)
    duration = float(probe(destination)['format']['duration'])
    if duration > 600:
        destination.unlink()
        raise ValueError('Each take is limited to 600 seconds; split long material into explicit segments')
    invalidate(db, project, storyboard=False)
    takes = {**project.music_state.get('takes', {})}
    selected = {**takes.get(segment.id, {})}
    if role == 'premixed':
        selected = {}  # Never put another instrumental underneath a premixed song.
    else:
        selected.pop('premixed', None)
    selected[role] = dict(path=destination.relative_to(settings.storage_root).as_posix(),
                          sha256=digest(destination), duration=duration, signature=signature(segment),
                          provenance=provenance)
    takes[segment.id] = selected
    project.music_state = {**project.music_state, 'takes': takes}


def execute(job_id, owner, operation, cancel):
    """One explicit operation per leased job; billable requests are never automatically retried."""
    from .music_audio import instrumental, mix, sing
    from .music_schema import MusicSegment
    from .queue import checkpoint, event
    with Session() as db:
        job = db.get(ProductionJob, job_id)
        project = db.get(VideoProject, job.project_id)
        project_id, revision = project.id, project.revision
        selection = job.checkpoint.get('_ai_selection')
    checkpoint(job_id, owner, 'AUDIO_GENERATION')
    with Session.begin() as db:
        row = db.get(ProductionJob, job_id)
        row.checkpoint = {**{k: v for k, v in row.checkpoint.items() if k != '_music_operation'},
                          '_last_music_operation': {**operation, 'status': 'started'}}
    event(project_id, 'AUDIO_GENERATION', 'Music operation started: '+operation['kind'])
    kind = operation['kind']
    if kind == 'assemble':
        from .music_compilation import assemble
        assemble(job_id, owner, cancel)
        with Session.begin() as db:
            row = db.get(ProductionJob, job_id)
            row.checkpoint = {**row.checkpoint, '_last_music_operation': {**operation, 'status': 'completed'}}
        event(project_id, 'HUMAN_REVIEW', 'Reviewed video units assembled; new human review required')
        return
    segment = next((s for s in MusicPlan.model_validate(project.music_plan).segments
                    if s.id == operation.get('segment_id')), None) if project.music_plan else None
    if cancel():
        raise Cancelled('Music operation cancelled')
    if kind in {'compose', 'regenerate'}:
        from .providers import get_provider, validate_selection
        from .visual_schema import catalog
        provider = get_provider(validate_selection(selection))
        context = dict(idea=project.idea, duration=project.target_duration, catalog=catalog(),
                       visual_selection=project.visual_config,
                       existing_plan=project.music_plan, selected_segment=segment.model_dump() if segment else None,
                       editorial_format=operation.get('format', 'musical_story'),
                       educational_goal=operation.get('goal', 'Friendship and cooperation'),
                       instructions='Original English lyrics and story. Lyrics follow visible actions. No copied songs. '
                       'Return compact JSON. Exact sum of segment durations. Use only available catalog. '
                       'A requested BPM is direction, never a measured beat. Regeneration changes only the selected segment.')
        result = provider.generate('Music Planner', context, MusicSegment if segment else MusicPlan,
                                   cancel=cancel, emit=lambda _: None)
        with provider.persistence_guard(), Session.begin() as db:
            current = db.get(VideoProject, project_id)
            if cancel() or current.revision != revision:
                raise Cancelled('Music production changed')
            if segment:
                if result.id != segment.id:
                    raise ValueError('Regenerated song must retain its segment ID')
                plan = MusicPlan.model_validate({**project.music_plan, 'segments': [
                    result.model_dump() if s['id'] == segment.id else s for s in project.music_plan['segments']]})
            else:
                plan = result
            save_plan(db, current, plan)
    elif kind == 'mix':
        destination, report = mix(project, cancel=cancel, progress=lambda n, total:
            event(project_id, 'AUDIO_GENERATION', f'Mix segment completed: {n}/{total}'))
        with Session.begin() as db:
            current = db.get(VideoProject, project_id)
            if cancel() or current.revision != revision:
                raise Cancelled('Mix changed during processing')
            from .final_audio import register
            register(current, destination, {'source': 'music-studio', 'report': report})
            current.music_state = {**current.music_state, 'mix_report': report}
            job = db.get(ProductionJob, job_id)
            job.checkpoint = {k: v for k, v in job.checkpoint.items() if k != '_music_operation'}
            job.state = current.status = 'PAUSED'
    else:
        if not segment:
            raise ValueError('Select an existing musical segment')
        directory = settings.storage_root/'music-work'/project_id/str(revision)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory/(segment.id+'-'+kind+'.wav')
        provenance = {'source': kind}
        if kind == 'instrumental':
            instrumental(segment, path, cancel=cancel)
            role = 'instrumental'
            provenance.update(generator='factory-additive-score-v1', license='Original procedural score',
                              bpm_requested=segment.bpm_requested, bpm_measured=None)
        elif kind == 'sing':
            try:
                source, song_id = sing(segment, directory, confirmed=operation.get('confirm_cost', False), cancel=cancel)
            except ConfigurationRequired as exc:
                raise MusicRequired(str(exc)) from exc
            path, role = source, 'premixed'
            provenance.update(provider='elevenlabs_music', model='music_v2_5', song_id=song_id,
                              vocal_review='Generated music; human listening required')
        elif kind == 'speech':
            from .audio import Piper
            if segment.kind not in {'dialogue', 'narration'}:
                raise ValueError('Piper generates speech only; use a song import or singing provider')
            path, role = Piper().generate(segment.text, cancel=cancel), 'speech'
            provenance['provider'] = 'piper_speech'
        else:
            raise ValueError('Unknown music operation')
        with Session.begin() as db:
            current = db.get(VideoProject, project_id)
            if cancel() or current.revision != revision:
                raise Cancelled('Music operation cancelled or changed')
            store_take(db, current, segment, Path(path), role, provenance)
    # Completion may create a new revision; never change an old cancelled job back to runnable.
    with Session.begin() as db:
        job = db.get(ProductionJob, job_id)
        job.checkpoint = {**{k: v for k, v in job.checkpoint.items() if k != '_music_operation'},
                          '_last_music_operation': {**operation, 'status': 'completed'}}
    event(project_id, 'WAITING_FOR_MUSIC', 'Music operation completed: '+kind)
