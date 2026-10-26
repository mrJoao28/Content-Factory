import hashlib
from datetime import timedelta, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from .api_helpers import no_running_job, project_or_404, serialize
from .config import settings
from .db import Session
from .models import (
    Channel,
    PlatformPublication,
    ProductionJob,
    PublishingSchedule,
    QualityReview,
    RenderArtifact,
    Series,
    VideoProject,
    utcnow,
)
from .publishing import approved, current_artifact, manual_package, publish, refresh_publication
from .queue import ACTIVE, WAITING, enqueue, event
from .schemas import (
    BatchCreate,
    DirectPost,
    ManualPublication,
    ProjectCreate,
    ProjectEdit,
    PublishRequest,
    Review,
    Schedule,
)
from .security import digest, safe_path

router = APIRouter()


@router.get("/projects")
def projects(channel_id: str | None = None):
    with Session() as db:
        query = select(VideoProject).order_by(VideoProject.created_at.desc()).limit(500)
        if channel_id:
            query = query.where(VideoProject.channel_id == channel_id)
        return [serialize(x) for x in db.scalars(query)]


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate):
    with Session.begin() as db:
        channel_id = body.channel_id
        if not channel_id:
            text = body.idea.lower()
            channel_id = (
                "wondernest"
                if any(x in text for x in ("child", "kid", "magical", "friendship", "color"))
                else "how-it-works"
            )
        data = body.model_dump()
        data["channel_id"] = channel_id
        if body.channel_id is None:
            data["target_duration"] = None
        body = ProjectCreate.model_validate(data)
        channel = db.get(Channel, channel_id)
        if body.series_id:
            series = db.get(Series, body.series_id)
            if not series or series.channel_id != channel_id:
                raise ValueError("Series not found in this channel")
        hashed = hashlib.sha256((channel_id + " " + " ".join(body.idea.lower().split())).encode()).hexdigest()
        existing = db.scalar(select(VideoProject).where(VideoProject.idea_hash == hashed))
        if existing:
            raise HTTPException(409, {"message": "Duplicate idea", "project_id": existing.id})
        landscape = body.content_type == "episode"
        project = VideoProject(
            channel_id=channel_id,
            series_id=body.series_id,
            title=body.idea[:80],
            idea=body.idea,
            idea_hash=hashed,
            platform=channel.platform,
            content_type=body.content_type,
            target_duration=body.target_duration,
            aspect_ratio="16:9" if landscape else "9:16",
            width=1280 if landscape else settings.render_default_width,
            height=720 if landscape else settings.render_default_height,
            fps=settings.render_default_fps,
        )
        db.add(project)
        db.flush()
        enqueue(db, project)
        result = serialize(project)
    event(project.id, "DRAFT", "Idea accepted and queued")
    return result


@router.get("/projects/{project_id}")
def project_detail(project_id: str):
    with Session() as db:
        project = project_or_404(db, project_id)
        result = serialize(project)
        for name, model in (
            ("jobs", ProductionJob),
            ("artifacts", RenderArtifact),
            ("reviews", QualityReview),
            ("publications", PlatformPublication),
        ):
            result[name] = [
                serialize(x)
                for x in db.scalars(
                    select(model).where(model.project_id == project_id).order_by(model.created_at.desc())
                )
            ]
        return result


@router.patch("/projects/{project_id}")
def edit_project(project_id: str, body: ProjectEdit):
    with Session.begin() as db:
        project = project_or_404(db, project_id)
        no_running_job(db, project_id)
        if not body.model_fields_set:
            raise ValueError("Supply script, storyboard or metadata")
        if body.script:
            project.script = body.script.model_dump(mode="json")
            project.storyboard = {}
            project.metadata_json = {}
        if body.storyboard:
            project.storyboard = body.storyboard.model_dump(mode="json")
        if body.metadata:
            project.metadata_json = body.metadata.model_dump()
        for job in db.scalars(
            select(ProductionJob).where(
                ProductionJob.project_id == project_id, ProductionJob.state.in_(ACTIVE | WAITING)
            )
        ):
            job.state = "CANCELLED"
        project.revision += 1
        project.approved_hash = None
        project.status = "DRAFT"
        return serialize(project)


@router.post("/projects/{project_id}/jobs/{action}")
def control_job(project_id: str, action: str):
    with Session.begin() as db:
        project = project_or_404(db, project_id)
        job = db.scalar(
            select(ProductionJob).where(
                ProductionJob.project_id == project_id, ProductionJob.revision == project.revision
            )
        )
        if action == "resume":
            no_running_job(db, project_id)
            if not job:
                job = enqueue(db, project)
            elif job.state not in WAITING | {"CANCELLED", "DRAFT"}:
                raise HTTPException(409, "Only waiting or stopped jobs may resume")
            job.state, job.error, job.available_at = "DRAFT", None, utcnow()
            job.owner, job.lease_until = None, None
            project.status = "DRAFT"
        elif action in {"pause", "cancel"}:
            if not job or job.state not in ACTIVE | WAITING:
                raise HTTPException(409, "No controllable job")
            job.state = "PAUSED" if action == "pause" else "CANCELLED"
            project.status = job.state
        else:
            raise HTTPException(404, "Unknown action")
        return serialize(job)


@router.post("/projects/{project_id}/review")
def review(project_id: str, body: Review):
    with Session.begin() as db:
        project = project_or_404(db, project_id)
        no_running_job(db, project_id)
        artifact = current_artifact(db, project)
        if not artifact or artifact.sha256 != body.artifact_hash:
            raise HTTPException(409, "Review the latest render of this revision")
        if digest(safe_path(settings.output_dir, artifact.path)) != artifact.sha256:
            raise ValueError("Render file was modified")
        if body.approved and (not artifact.probe.get("checks") or not all(artifact.probe["checks"].values())):
            raise ValueError("Technical checks failed")
        if body.approved and project.channel_id == "how-it-works" and not body.scientific_sources_checked:
            raise ValueError("Verify scientific sources before approval")
        db.add(
            QualityReview(
                project_id=project_id,
                artifact_hash=artifact.sha256,
                approved=body.approved,
                notes=body.notes,
                checks={"scientific_sources_checked": body.scientific_sources_checked},
            )
        )
        project.approved_hash = artifact.sha256 if body.approved else None
        project.status = "APPROVED" if body.approved else "HUMAN_REVIEW"
        return serialize(project)


@router.get("/projects/{project_id}/media/{kind}")
def project_media(project_id: str, kind: str):
    with Session() as db:
        artifact = current_artifact(db, project_or_404(db, project_id))
        if not artifact:
            raise HTTPException(404, "No render for current revision")
        movie = safe_path(settings.output_dir, artifact.path)
        filename = {
            "video": "video.mp4",
            "thumbnail": "thumbnail.png",
            "captions": "captions.srt",
            "metadata": "metadata.json",
            "script": "script.json",
        }.get(kind)
        if not filename or not (movie.parent / filename).is_file():
            raise HTTPException(404, "Artifact missing")
        return FileResponse(movie.parent / filename)


@router.get("/calendar")
def calendar():
    with Session() as db:
        return [
            serialize(x)
            for x in db.scalars(select(PublishingSchedule).order_by(PublishingSchedule.scheduled_at))
        ]


@router.post("/projects/{project_id}/schedule")
def schedule(project_id: str, body: Schedule):
    when = body.scheduled_at.astimezone(timezone.utc)
    if when <= utcnow():
        raise ValueError("Choose a future time")
    with Session.begin() as db:
        project = project_or_404(db, project_id)
        if body.mode == "youtube" and project.platform != "youtube":
            raise ValueError("TikTok has no native scheduling in this application")
        conflict = db.scalar(
            select(PublishingSchedule)
            .join(VideoProject)
            .where(
                VideoProject.channel_id == project.channel_id,
                PublishingSchedule.project_id != project_id,
                PublishingSchedule.scheduled_at >= when - timedelta(seconds=60),
                PublishingSchedule.scheduled_at <= when + timedelta(seconds=60),
            )
        )
        if conflict:
            raise HTTPException(409, "Channel already has a publication within one minute")
        row = db.scalar(select(PublishingSchedule).where(PublishingSchedule.project_id == project_id))
        if row and row.status in {"SCHEDULED", "PUBLISHED"}:
            raise HTTPException(409, "Change the confirmed remote schedule on the platform first")
        if not row:
            row = PublishingSchedule(project_id=project_id, scheduled_at=when, timezone=body.timezone)
            db.add(row)
        row.scheduled_at, row.timezone, row.mode, row.status = when, body.timezone, body.mode, "PLANNED"
        db.flush()
        return serialize(row)


@router.delete("/projects/{project_id}/schedule")
def delete_schedule(project_id: str):
    with Session.begin() as db:
        row = db.scalar(select(PublishingSchedule).where(PublishingSchedule.project_id == project_id))
        if row and row.status in {"SCHEDULED", "PUBLISHED"}:
            raise HTTPException(409, "Cancel the remote schedule on the platform first")
        if row:
            db.delete(row)
    return {"deleted": True}


@router.post("/projects/{project_id}/manual-package")
def package(project_id: str):
    manual_package(project_id)
    return {"download": f"/projects/{project_id}/manual-package"}


@router.get("/projects/{project_id}/manual-package")
def download_package(project_id: str):
    with Session() as db:
        _, movie = approved(db, project_or_404(db, project_id))
        path = movie.parent / "manual-post.zip"
        if not path.exists():
            raise HTTPException(404, "Prepare the package first")
        return FileResponse(path, filename="manual-post.zip")


@router.post("/projects/{project_id}/manual-publication")
def register_manual(project_id: str, body: ManualPublication):
    with Session.begin() as db:
        project = project_or_404(db, project_id)
        artifact, _ = approved(db, project)
        url = urlparse(body.url)
        hosts = {
            "youtube": {"www.youtube.com", "youtube.com", "youtu.be"},
            "tiktok": {"www.tiktok.com", "tiktok.com"},
        }
        if url.scheme != "https" or url.hostname not in hosts[project.platform] or not url.path.strip("/"):
            raise ValueError("Provide the final HTTPS URL on the correct platform")
        row = db.scalar(
            select(PlatformPublication).where(
                PlatformPublication.project_id == project_id,
                PlatformPublication.platform == project.platform,
                PlatformPublication.artifact_hash == artifact.sha256,
            )
        )
        if not row:
            row = PlatformPublication(
                project_id=project_id,
                platform=project.platform,
                artifact_hash=artifact.sha256,
                status="MANUAL_CONFIRMED",
            )
            db.add(row)
        row.status, row.url = "MANUAL_CONFIRMED", body.url
        row.details = {"confirmation": "user", "api_verified": False}
        project.status = "PUBLISHED"
        return {"status": "MANUAL_CONFIRMED", "api_verified": False}


@router.post("/projects/{project_id}/publish/{platform}")
def publish_project(project_id: str, platform: str, body: PublishRequest):
    if not body.confirm:
        raise ValueError("Explicit upload/publication confirmation required")
    publication_id = publish(project_id, platform, body.privacy)
    with Session() as db:
        return serialize(db.get(PlatformPublication, publication_id))


@router.post("/publications/{publication_id}/refresh")
def publication_refresh(publication_id: str):
    return {"status": refresh_publication(publication_id)}


@router.get("/integrations/tiktok/creator")
def tiktok_creator():
    from .integrations import TikTok

    return {
        "direct_post_enabled": settings.tiktok_direct_post_enabled,
        "creator": TikTok().creator_info() if settings.tiktok_direct_post_enabled else None,
    }


@router.post("/projects/{project_id}/tiktok-direct")
def tiktok_direct(project_id: str, body: DirectPost):
    from .publishing import direct_post

    publication_id = direct_post(project_id, body)
    with Session() as db:
        return serialize(db.get(PlatformPublication, publication_id))


@router.post("/publications/{publication_id}/thumbnail")
def youtube_thumbnail(publication_id: str):
    from .integrations import Google

    with Session() as db:
        row = db.get(PlatformPublication, publication_id)
        if not row or row.platform != "youtube" or not row.remote_id:
            raise ValueError("YouTube upload with a confirmed video ID is required")
        project = project_or_404(db, row.project_id)
        artifact, movie = approved(db, project)
        if row.artifact_hash != artifact.sha256:
            raise ValueError("Publication is from an older revision")
        thumbnail = movie.parent / "thumbnail.png"
        if not thumbnail.is_file() or thumbnail.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Thumbnail missing or exceeds YouTube 2MB limit")
        with thumbnail.open("rb") as source:
            response = (
                Google("youtube")
                .request(
                    "POST",
                    "https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
                    params={"videoId": row.remote_id, "uploadType": "media"},
                    headers={"Content-Type": "image/png"},
                    content=source.read(),
                )
                .json()
            )
    with Session.begin() as db:
        row = db.get(PlatformPublication, publication_id)
        row.details = {**row.details, "thumbnail_response": response}
    return {"confirmed": True, "response": response}


@router.post("/projects/batch", status_code=207)
def batch_create(body: BatchCreate):
    results, errors = [], []
    for index, idea in enumerate(body.ideas):
        try:
            results.append(create_project(idea))
        except HTTPException as exc:
            errors.append({"index": index, "detail": exc.detail})
        except ValueError as exc:
            errors.append({"index": index, "detail": str(exc)})
    return {"projects": results, "errors": errors}
