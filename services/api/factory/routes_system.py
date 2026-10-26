import asyncio
import json
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import select

from .api_helpers import serialize
from .codex import auth_status, start_login
from .config import settings
from .db import Session
from .integrations import Google, OAuth, TikTok
from .models import (Channel, JobEvent, PlatformConnection, PlatformPublication, ProductionJob,
                     RenderArtifact, UserSettings, VideoProject)
from .queue import ACTIVE

router = APIRouter()


@router.get("/health")
def health():
    with Session() as db:
        db.execute(select(1))
    return {"state": "READY", "database": "sqlite-wal"}


@router.get("/channels")
def channels():
    with Session() as db:
        return [serialize(x) for x in db.scalars(select(Channel))]


@router.get("/dashboard")
def dashboard(channel_id: str | None = None):
    with Session() as db:
        query = select(VideoProject)
        if channel_id:
            query = query.where(VideoProject.channel_id == channel_id)
        projects = list(db.scalars(query))
        ids = [p.id for p in projects]
        artifacts = list(db.scalars(select(RenderArtifact).where(RenderArtifact.project_id.in_(ids))))
        publications = list(db.scalars(select(PlatformPublication).where(PlatformPublication.project_id.in_(ids))))
        def count(states):
            return sum(p.status in states for p in projects)
        sizes = sum(p.stat().st_size for root in (settings.storage_root, settings.output_dir, settings.assets_dir)
                    for p in root.rglob("*") if p.is_file())
        return {"projects": len(projects), "queued": count({"DRAFT"}), "running": count(ACTIVE-{"DRAFT"}),
                "rendered": len({a.project_id for a in artifacts}), "approved": sum(bool(p.approved_hash) for p in projects),
                "drive_uploaded": len({p.project_id for p in publications if p.platform == "drive" and p.status == "UPLOADED"}),
                "scheduled": sum(p.status == "SCHEDULED" for p in publications),
                "published": len({p.project_id for p in publications if p.status in {"PUBLISHED", "MANUAL_CONFIRMED"}}),
                "failures": count({"FAILED"}), "storage_bytes": sizes,
                "average_render_seconds": sum(a.render_seconds for a in artifacts)/len(artifacts) if artifacts else None,
                "external_metrics": None}


@router.get("/jobs")
def jobs():
    with Session() as db:
        return [serialize(x) for x in db.scalars(select(ProductionJob).order_by(ProductionJob.created_at.desc()).limit(500))]


@router.get("/events")
def events(project_id: str | None = None, after: int = 0):
    with Session() as db:
        query = select(JobEvent).where(JobEvent.id > after)
        query = query.order_by(JobEvent.id if after else JobEvent.id.desc()).limit(500)
        if project_id:
            query = query.where(JobEvent.project_id == project_id)
        rows = [serialize(x) for x in db.scalars(query)]
        return rows if after else list(reversed(rows))


@router.get("/events/stream")
async def event_stream(request: Request, project_id: str | None = None, after: int = 0):
    async def stream():
        cursor = after
        try:
            cursor = max(cursor, int(request.headers.get("last-event-id", "0")))
        except ValueError:
            pass
        while not await request.is_disconnected():
            rows = await asyncio.to_thread(events, project_id, cursor)
            for row in rows:
                cursor = row["id"]
                yield f"id: {cursor}\ndata: {json.dumps(row)}\n\n"
            if not rows:
                yield ": heartbeat\n\n"
            await asyncio.sleep(1)
    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/auth/codex")
def codex_connection():
    return auth_status()


@router.post("/auth/codex/connect")
def codex_connect():
    return start_login()


@router.get("/connections")
def connections():
    with Session() as db:
        return [serialize(x) for x in db.scalars(select(PlatformConnection))]


@router.post("/auth/{platform}/connect")
def oauth_connect(platform: str):
    return {"url": OAuth().start(platform)}


@router.get("/auth/google/callback", response_class=HTMLResponse)
def google_callback(state: str, code: str):
    platform = OAuth().complete(state, code, {"google", "youtube"})
    if platform not in {"google", "youtube"}:
        raise ValueError("OAuth provider mismatch")
    return "<h1>Connected</h1><p>Return to AI Content Factory. You can close this tab.</p>"


@router.get("/auth/tiktok/callback", response_class=HTMLResponse)
def tiktok_callback(state: str, code: str):
    OAuth().complete(state, code, "tiktok")
    return "<h1>Connected</h1><p>Return to AI Content Factory.</p>"


@router.post("/auth/{platform}/disconnect")
def disconnect(platform: str):
    if platform not in {"google", "youtube", "tiktok"}:
        raise ValueError("Unsupported platform")
    OAuth().disconnect(platform)
    return {"state": "AUTH_REQUIRED"}


@router.get("/integrations/{platform}/identity")
def identity(platform: str):
    if platform == "tiktok":
        return TikTok().identity()
    if platform in {"google", "youtube"}:
        return Google(platform).identity()
    raise HTTPException(404, "Unknown platform")


@router.get("/integrations/drive/folders")
def drive_folders():
    return Google().folders()


@router.post("/integrations/drive/layout")
def drive_layout():
    return Google().drive_layout()


@router.get("/settings")
def user_settings():
    with Session() as db:
        row = db.get(UserSettings, "preferences")
        return {"timezone": settings.default_timezone, "require_human_approval": settings.require_human_approval,
                "auto_publish": False, "render_concurrency": 1, "voice_configured": bool(settings.piper_voice_path),
                **(row.values if row else {})}


@router.patch("/settings")
def update_settings(body: dict):
    if set(body)-{"timezone", "editorial_goals", "drive_folder_id"}:
        raise ValueError("Unsupported setting; edit local .env for system configuration")
    if "timezone" in body:
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(body["timezone"])
        except (KeyError, TypeError) as exc:
            raise ValueError("Unknown IANA timezone") from exc
    if "drive_folder_id" in body and not re.fullmatch(r"[a-zA-Z0-9_-]{1,200}", body["drive_folder_id"]):
        raise ValueError("Invalid Drive folder ID")
    if len(json.dumps(body)) > 8000:
        raise ValueError("Settings too large")
    with Session.begin() as db:
        row = db.get(UserSettings, "preferences")
        if not row:
            row = UserSettings(id="preferences", values={})
            db.add(row)
        row.values = {**row.values, **body}
    return user_settings()


@router.get("/doctor")
def doctor():
    from .doctor import diagnose
    return diagnose()


@router.get("/analytics")
def analytics(channel_id: str):
    from .models import AnalyticsSnapshot
    with Session() as db:
        return [serialize(x) for x in db.scalars(select(AnalyticsSnapshot).where(
            AnalyticsSnapshot.channel_id == channel_id).order_by(AnalyticsSnapshot.created_at.desc()).limit(60))]


@router.post("/analytics/sync/youtube")
def sync_youtube_analytics():
    from .models import AnalyticsSnapshot
    response = Google("youtube").identity()
    items = response.get("items", [])
    if not items or (settings.youtube_channel_id and items[0]["id"] != settings.youtube_channel_id):
        raise ValueError("Verify the expected YouTube channel before syncing")
    metrics = {"channel_id": items[0]["id"], "statistics": items[0].get("statistics", {}),
               "retention": None, "watch_time": None}
    with Session.begin() as db:
        row = AnalyticsSnapshot(channel_id="wondernest", source="youtube-data-api", metrics=metrics)
        db.add(row)
        db.flush()
        return serialize(row)
