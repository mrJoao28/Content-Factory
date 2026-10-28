from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import Field, SecretStr
from sqlalchemy import select, text

from .api_helpers import no_running_job, project_or_404, serialize
from .config import settings
from .db import Session
from .models import MusicVersion
from .music import save_plan, store_take, take_path, timeline
from .music_schema import MusicPlan
from .queue import enqueue
from .routes_library import save_upload
from .schemas import Strict
from .security import Vault

router = APIRouter()


@router.get('/music/units')
def units():
    from .models import RenderArtifact, VideoProject
    with Session() as db:
        return [dict(project_id=p.id, title=p.title, sha256=a.sha256, duration=p.target_duration,
                     width=p.width, height=p.height, fps=p.fps,
                     character=p.visual_config.get('character', 'dino'))
                for p, a in db.execute(select(VideoProject, RenderArtifact).join(RenderArtifact,
                    RenderArtifact.project_id == VideoProject.id).where(
                    VideoProject.approved_hash == RenderArtifact.sha256,
                    VideoProject.revision == RenderArtifact.revision).limit(200))]


class PlanEdit(Strict):
    revision: int
    plan: MusicPlan
    target_duration: float | None = Field(default=None, ge=8, le=3600)


class Operation(Strict):
    revision: int
    kind: Literal['compose', 'regenerate', 'instrumental', 'sing', 'speech', 'mix', 'assemble']
    segment_id: str | None = None
    format: Literal['animated_song', 'musical_story', 'musical_episode', 'compilation'] = 'musical_story'
    goal: str = Field(default='Friendship and cooperation', max_length=1000)
    confirm_cost: bool = False


class MusicCredential(Strict):
    api_key: SecretStr = Field(min_length=10, max_length=512)


@router.post('/music/elevenlabs')
def configure(body: MusicCredential):
    Vault().put('elevenlabs_music', {'api_key': body.api_key.get_secret_value()})
    return {'stored': True, 'verified': False}


@router.delete('/music/elevenlabs')
def disconnect():
    Vault().delete('elevenlabs_music')
    return {'deleted': True}


@router.get('/projects/{project_id}/music')
def studio(project_id: str):
    with Session() as db:
        project = project_or_404(db, project_id)
        return {'revision': project.revision, 'plan': project.music_plan, 'audio': project.music_state,
                'timeline': timeline(project), 'final': project.narration.get('final'),
                'history': [serialize(v) for v in db.scalars(select(MusicVersion).where(
                    MusicVersion.project_id == project_id).order_by(MusicVersion.created_at.desc()).limit(100))]}


@router.patch('/projects/{project_id}/music')
def edit(project_id: str, body: PlanEdit):
    with Session.begin() as db:
        db.execute(text('BEGIN IMMEDIATE'))
        project = project_or_404(db, project_id)
        no_running_job(db, project_id)
        if project.revision != body.revision:
            raise HTTPException(409, 'Revision changed; refresh the Music Studio')
        if body.target_duration is not None:
            if abs(body.target_duration*project.fps-round(body.target_duration*project.fps)) > .000001:
                raise ValueError('Project duration must represent whole frames')
            project.target_duration = body.target_duration
        save_plan(db, project, body.plan)
        return {'revision': project.revision, 'timeline': timeline(project)}


@router.post('/projects/{project_id}/music/operations', status_code=202)
def operation(project_id: str, body: Operation):
    with Session.begin() as db:
        db.execute(text('BEGIN IMMEDIATE'))
        project = project_or_404(db, project_id)
        no_running_job(db, project_id)
        if body.revision != project.revision:
            raise HTTPException(409, 'Revision changed')
        if project.visual_config.get('engine') != 'blender_3d':
            raise ValueError('Select Blender 3D explicitly before composing a musical production')
        if body.kind == 'sing' and not body.confirm_cost:
            raise ValueError('Confirm the paid music request explicitly; import is available without this service')
        if body.kind not in {'compose', 'mix', 'assemble'}:
            plan = MusicPlan.model_validate(project.music_plan)
            if not any(s.id == body.segment_id for s in plan.segments):
                raise ValueError('Segment not found')
            segment = next(s for s in plan.segments if s.id == body.segment_id)
            if segment.kind in {'unit', 'pause'}:
                raise ValueError('Edit pauses and reviewed compilation units directly in the plan')
        if body.kind == 'mix' and (not project.music_plan or any(r['conflict'] for r in timeline(project))):
            raise ValueError('Resolve timeline conflicts before mixing')
        if body.kind == 'assemble':
            if project.music_plan.get('format') != 'compilation':
                raise ValueError('Choose a compilation plan first')
            from .music_compilation import sources
            sources(db, project)
        job = enqueue(db, project)
        if job.checkpoint.get('_music_operation'):
            raise HTTPException(409, 'A music operation is already queued; cancel it before replacing')
        job.checkpoint = {**job.checkpoint, '_music_operation': body.model_dump(exclude={'revision'})}
        job.state, job.error, job.attempts = 'DRAFT', None, 0
        project.status = job.state
        return {'job_id': job.id, 'state': job.state}


@router.post('/projects/{project_id}/music/{segment_id}/import')
async def import_song(project_id: str, segment_id: str, revision: int = Form(...), rights: str = Form(...),
                      role: Literal['premixed', 'vocals', 'instrumental', 'speech', 'effects'] = Form('premixed'),
                      file: UploadFile = File(...)):
    if not rights.strip() or len(rights) > 3000:
        raise ValueError('Declare the origin and rights for the imported audio')
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in {'.wav', '.mp3'}:
        raise ValueError('Import WAV or MP3 audio')
    path = await save_upload(file, settings.storage_root/'music-imports', suffix)
    try:
        with Session.begin() as db:
            db.execute(text('BEGIN IMMEDIATE'))
            project = project_or_404(db, project_id)
            no_running_job(db, project_id)
            if project.revision != revision:
                raise HTTPException(409, 'Revision changed')
            plan = MusicPlan.model_validate(project.music_plan)
            segment = next((s for s in plan.segments if s.id == segment_id), None)
            if not segment:
                raise ValueError('Segment not found')
            if segment.kind == 'pause' or (segment.kind == 'song' and role == 'speech'):
                raise ValueError('Speech is not a sung song')
            store_take(db, project, segment, path, role, {'source': 'import', 'rights': rights})
            return {'revision': project.revision, 'timeline': timeline(project)}
    finally:
        path.unlink(missing_ok=True)


@router.get('/projects/{project_id}/music/{segment_id}/audio/{role}')
def preview(project_id: str, segment_id: str, role: str):
    with Session() as db:
        project = project_or_404(db, project_id)
        take = project.music_state.get('takes', {}).get(segment_id, {}).get(role)
        if not take:
            raise HTTPException(404, 'No selected take')
        return FileResponse(take_path(take), media_type='audio/wav')
