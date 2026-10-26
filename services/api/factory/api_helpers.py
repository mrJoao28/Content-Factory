from datetime import timezone

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import inspect, select

from .models import PlatformPublication, ProductionJob, VideoProject, utcnow


def serialize(row):
    if row is None:
        return None
    values = {column.key: getattr(row, column.key) for column in inspect(type(row)).column_attrs}
    if "metadata_json" in values:
        values["metadata"] = values.pop("metadata_json")
    values.pop("idea_hash", None)
    return jsonable_encoder(values)


def project_or_404(db, project_id):
    row = db.get(VideoProject, project_id)
    if not row:
        raise HTTPException(404, "Project not found")
    return row


def no_running_job(db, project_id):
    uploading = db.scalar(
        select(PlatformPublication.id).where(
            PlatformPublication.project_id == project_id, PlatformPublication.status == "UPLOADING"
        )
    )
    if uploading:
        raise HTTPException(409, "Wait for the active upload to finish before editing")
    running = db.scalar(
        select(ProductionJob).where(ProductionJob.project_id == project_id, ProductionJob.owner.is_not(None))
    )
    if running and running.lease_until and running.lease_until.replace(tzinfo=timezone.utc) > utcnow():
        raise HTTPException(409, "Pause the worker and wait for it to release this project")
