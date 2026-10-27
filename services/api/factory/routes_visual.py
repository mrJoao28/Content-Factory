"""Visual production controls use the application's existing local mutation guards."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import select, text

from .api_helpers import no_running_job, project_or_404
from .audio import Piper
from .db import Session
from .models import ProductionJob
from .queue import enqueue, event
from .security import ConfigurationRequired
from .visual_audio import audible_wav, voice_info
from .visual_render import blender_info
from .visual_schema import Data, VisualSettings, catalog

router = APIRouter()
DEPENDENT = ["storyboard_planner", "visual_director", "animation_planner", "quality_reviewer", "publishing_assistant", "audio"]


@router.get("/visual/catalog")
def visual_catalog():
    result = catalog()
    try:
        info = blender_info()
        result["blender"] = {"state": "CONFIGURED", "version": info["version"], "engine": "CYCLES CPU",
                             "message": "Run doctor smoke render to verify CPU rendering on this machine."}
    except (ConfigurationRequired, RuntimeError) as exc:
        result["blender"] = {"state": "UNAVAILABLE", "message": str(exc)}
    try:
        result["voice"] = voice_info()
    except ConfigurationRequired as exc:
        result["voice"] = {"state": "MISSING_CONFIG", "message": str(exc)}
    return result


@router.post("/visual/voice-test")
def voice_test():
    voice_info()
    path = Piper().generate("Hello! Welcome to our little world of discovery.")
    audible_wav(path)
    from .render import probe
    if float(probe(path)["format"]["duration"]) < .1:
        raise ConfigurationRequired("Voice test returned empty audio")
    return FileResponse(path, media_type="audio/wav", filename="voice-test.wav")


class Regenerate(Data):
    expected_revision: int = Field(ge=1)
    confirm_invalidation: bool


class VisualUpdate(Regenerate):
    visual: VisualSettings


def revise(project_id, body, change=None):
    if not body.confirm_invalidation:
        raise ValueError("Confirm invalidation of dependent planning, renders and approval")
    with Session.begin() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        project = project_or_404(db, project_id)
        no_running_job(db, project_id)
        if project.revision != body.expected_revision:
            raise HTTPException(409, "Revision changed; refresh before trying again")
        old = db.scalar(select(ProductionJob).where(ProductionJob.project_id == project_id,
                                                   ProductionJob.revision == project.revision))
        saved = dict(old.checkpoint) if old else {}
        if change:
            if change.engine == "blender_3d":
                blender_info()
            project.visual_config = change.model_dump(mode="json")
            project.width, project.height = map(int, change.resolution.split("x"))
            project.fps = change.fps
        if old:
            old.state, old.owner, old.lease_until = "CANCELLED", None, None
        project.revision += 1
        project.approved_hash, project.status = None, "DRAFT"
        project.storyboard, project.metadata_json = {}, {}
        project.narration = {k: v for k, v in project.narration.items() if k != "generated_path"}
        job = enqueue(db, project)
        keep = {"creative_director", "script_writer", "_ai_selection", "_ai_selection_history"}
        job.checkpoint = {**job.checkpoint, **{k: v for k, v in saved.items() if k in keep}}
        job.checkpoint["_ai_step_sources"] = {k: v for k, v in saved.get("_ai_step_sources", {}).items() if k in keep}
        job.checkpoint["_visual_regenerated_from_revision"] = body.expected_revision
        result = {"revision": project.revision, "job_id": job.id, "invalidated": DEPENDENT,
                  "preserved": [k for k in ("creative_director", "script_writer") if k in saved]}
    event(project_id, "DRAFT", "Visual planning regeneration requested; script retained; dependent renders and approval invalidated")
    return result


@router.post("/projects/{project_id}/visual/regenerate")
def regenerate(project_id: str, body: Regenerate):
    return revise(project_id, body)


@router.post("/projects/{project_id}/visual/settings")
def update_visual(project_id: str, body: VisualUpdate):
    return revise(project_id, body, change=body.visual)
