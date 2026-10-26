import threading
import zipfile
from datetime import timezone

from sqlalchemy import select

from .config import settings
from .db import Session
from .integrations import Google, PlatformError, TikTok
from .models import Channel, PlatformPublication, PublishingSchedule, RenderArtifact, VideoProject, utcnow
from .security import ConfigurationRequired, digest, safe_path

publish_lock = threading.Lock()


def current_artifact(db, project):
    return db.scalar(
        select(RenderArtifact)
        .where(RenderArtifact.project_id == project.id, RenderArtifact.revision == project.revision)
        .order_by(RenderArtifact.created_at.desc())
        .limit(1)
    )


def approved(db, project):
    artifact = current_artifact(db, project)
    if not artifact:
        raise ValueError("Render this revision before publishing")
    path = safe_path(settings.output_dir, artifact.path)
    if not path.is_file() or digest(path) != artifact.sha256:
        raise ValueError("Rendered file changed; render and approve again")
    # Even with REQUIRE_HUMAN_APPROVAL=false, publication still requires an explicit API action.
    if settings.require_human_approval and project.approved_hash != artifact.sha256:
        raise ValueError("Human approval required for the current artifact")
    if not project.metadata_json.get("title"):
        raise ValueError("Publication metadata is missing")
    return artifact, path


def manual_package(project_id):
    with Session.begin() as db:
        project = db.get(VideoProject, project_id)
        artifact, movie = approved(db, project)
        destination = movie.parent / "manual-post.zip"
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as package:
            for name in ["video.mp4", "thumbnail.png", "script.json", "captions.srt", "metadata.json"]:
                path = movie.parent / name
                if path.is_file():
                    package.write(path, name)
            package.writestr(
                "caption.txt",
                project.metadata_json.get("description", "")
                + "\n"
                + " ".join("#" + tag.replace(" ", "") for tag in project.metadata_json.get("tags", [])),
            )
            package.writestr(
                "posting-instructions.txt",
                "Prepared locally. Not uploaded or published.\n"
                "Use YouTube Studio or TikTok to post. Review privacy, audience, music rights and date.\n",
            )
        project.status = "READY_FOR_MANUAL_POST"
        return destination


def publish(project_id, platform, privacy="private"):
    if platform not in {"drive", "youtube", "tiktok"}:
        raise ValueError("Unsupported platform")
    with publish_lock:
        with Session.begin() as db:
            project = db.get(VideoProject, project_id)
            if not project:
                raise ValueError("Project not found")
            artifact, path = approved(db, project)
            if platform != "drive" and platform != project.platform:
                raise ValueError("Publication platform must match the channel")
            publication = db.scalar(
                select(PlatformPublication).where(
                    PlatformPublication.project_id == project_id,
                    PlatformPublication.platform == platform,
                    PlatformPublication.artifact_hash == artifact.sha256,
                )
            )
            if publication and publication.status in {
                "UPLOADED",
                "PUBLISHED",
                "SCHEDULED",
                "MANUAL_CONFIRMED",
            }:
                return publication.id
            if publication and publication.status == "UPLOADING":
                raise ValueError("Upload in progress or interrupted; query status before retrying")
            if publication and publication.status == "NEEDS_RECONCILIATION":
                raise ValueError("Ambiguous external result: reconcile remote account before another upload")
            if not publication:
                publication = PlatformPublication(
                    project_id=project_id, platform=platform, artifact_hash=artifact.sha256, status="PREPARED"
                )
                db.add(publication)
                db.flush()
            publication_id = publication.id
            metadata = dict(project.metadata_json)
            channel = db.get(Channel, project.channel_id)
            schedule = db.scalar(
                select(PublishingSchedule).where(PublishingSchedule.project_id == project_id)
            )
            project_info = {
                "channel": channel.name,
                "kids": channel.made_for_kids,
                "type": project.content_type,
                "project_id": project.id,
            }
        # Check auth before marking an externally ambiguous operation.
        if platform == "tiktok":
            client = TikTok()
            client.oauth.token("tiktok")
        else:
            client = Google("youtube" if platform == "youtube" else "google")
            client.oauth.token(client.platform)
        with Session.begin() as db:
            row = db.get(PlatformPublication, publication_id)
            row.status = "UPLOADING"
        last_upload_key = None
        try:
            if platform == "drive":
                layout = client.drive_layout()
                sub = (
                    "Episodes"
                    if project_info["type"] == "episode"
                    else "Shorts"
                    if project_info["kids"]
                    else "Videos"
                )
                parent = layout[project_info["channel"] + "/" + sub]
                uploaded = []
                for name in ["video.mp4", "thumbnail.png", "script.json", "metadata.json", "captions.srt"]:
                    file = path.parent / name
                    if not file.is_file():
                        continue
                    key = f"{project_id}-{artifact.sha256}-{name}"
                    last_upload_key = key
                    result = client.upload(
                        file,
                        {
                            "name": metadata["title"] + " - " + name,
                            "parents": [parent],
                            "appProperties": {"factoryKey": key},
                        },
                        key,
                    )
                    if not result.get("id"):
                        raise PlatformError("drive", code="missing_remote_id")
                    uploaded.append({"name": name, "id": result["id"], "url": result.get("webViewLink", "")})
                result_id = uploaded[0]["id"]
                url = "https://drive.google.com/file/d/" + result_id + "/view"
                details = {"files": uploaded}
                status = "UPLOADED"
            elif platform == "youtube":
                identity = client.identity().get("items", [])
                if not identity or (
                    settings.youtube_channel_id and identity[0]["id"] != settings.youtube_channel_id
                ):
                    raise ValueError("YouTube authenticated channel does not match configured channel")
                body = {
                    "snippet": {
                        "title": metadata["title"],
                        "description": metadata.get("description", ""),
                        "tags": metadata.get("tags", []),
                        "defaultLanguage": "en",
                    },
                    "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": project_info["kids"]},
                }
                if schedule and schedule.mode == "youtube":
                    when = (
                        schedule.scheduled_at.replace(tzinfo=timezone.utc)
                        if schedule.scheduled_at.tzinfo is None
                        else schedule.scheduled_at
                    )
                    if when <= utcnow():
                        raise ValueError("Scheduled publishAt must be in the future")
                    body["status"]["privacyStatus"] = "private"
                    body["status"]["publishAt"] = when.isoformat().replace("+00:00", "Z")
                last_upload_key = artifact.sha256
                result = client.upload(path, body, artifact.sha256, youtube=True)
                if not result.get("id"):
                    raise PlatformError("youtube", code="missing_remote_id")
                result_id = result["id"]
                url = "https://www.youtube.com/watch?v=" + result_id
                details = {"api_status": result.get("status", {})}
                status = "UPLOADED"  # Query processing/privacy status before claiming publication.
            else:
                result = client.init_inbox(path)
                result_id = result["publish_id"]
                # Persist the API ID before transferring bytes, so interrupted uploads remain diagnosable.
                with Session.begin() as db:
                    row = db.get(PlatformPublication, publication_id)
                    row.remote_id = result_id
                client.transfer(path, result["upload_url"])
                url, status = "", "UPLOADED"
                details = {
                    "mode": "inbox",
                    "instructions": "Finish posting inside TikTok. Upload does not confirm publication.",
                }
            with Session.begin() as db:
                row = db.get(PlatformPublication, publication_id)
                row.remote_id, row.url, row.status, row.details = result_id, url, status, details
                if platform == "drive":
                    db.get(VideoProject, project_id).status = "PUBLICATION_PREPARATION"
            return publication_id
        except Exception:
            resumable = False
            if platform != "tiktok" and last_upload_key:
                token = client.oauth.vault.get(client.platform) or {}
                resumable = last_upload_key in token.get("upload_sessions", {})
            with Session.begin() as db:
                db.get(PlatformPublication, publication_id).status = (
                    "INTERRUPTED" if resumable else "NEEDS_RECONCILIATION"
                )
            raise


def refresh_publication(publication_id):
    with Session() as db:
        row = db.get(PlatformPublication, publication_id)
        if not row or not row.remote_id:
            raise ValueError("No remote ID to query")
        platform, remote_id = row.platform, row.remote_id
    if platform == "youtube":
        response = Google("youtube").video_status(remote_id)
        items = response.get("items", [])
        if not items:
            raise ValueError("YouTube did not return the video")
        status = items[0].get("status", {})
        confirmed = status.get("uploadStatus") == "processed" and status.get("privacyStatus") == "public"
        scheduled = bool(status.get("publishAt")) and status.get("privacyStatus") == "private"
        outcome = "PUBLISHED" if confirmed else "SCHEDULED" if scheduled else "UPLOADED"
    elif platform == "tiktok":
        response = TikTok().status(remote_id)
        # Inbox status SEND_TO_USER_INBOX is never equivalent to publication.
        outcome = "PUBLISHED" if response.get("status") == "PUBLISH_COMPLETE" else "UPLOADED"
    else:
        raise ValueError("Drive file uploads have no publication state")
    with Session.begin() as db:
        row = db.get(PlatformPublication, publication_id)
        row.status = outcome
        row.details = {**row.details, "remote_status": response}
        if outcome in {"PUBLISHED", "SCHEDULED"}:
            db.get(VideoProject, row.project_id).status = outcome
        schedule = db.scalar(
            select(PublishingSchedule).where(PublishingSchedule.project_id == row.project_id)
        )
        if schedule and outcome in {"PUBLISHED", "SCHEDULED"}:
            schedule.status = outcome
    return outcome


def direct_post(project_id, request):
    if not settings.tiktok_direct_post_enabled:
        raise ConfigurationRequired(
            "Direct Post disabled. Obtain TikTok approval, then enable and reconnect OAuth."
        )
    if not request.confirm or not request.music_usage_confirmed:
        raise ValueError("Confirm posting and TikTok music usage terms")
    with publish_lock:
        client = TikTok()
        client.oauth.token("tiktok")
        token = client.oauth.vault.get("tiktok")
        if "video.publish" not in token.get("scope", "").replace(",", " ").split():
            raise ConfigurationRequired("TikTok video.publish scope not granted; reconnect after approval")
        creator = client.creator_info()
        if request.privacy_level not in creator.get("privacy_level_options", []):
            raise ValueError("Select a current privacy option returned by TikTok")
        for permission in ("duet", "stitch", "comment"):
            if creator.get(permission + "_disabled") and not getattr(request, "disable_" + permission):
                raise ValueError("Interaction disabled by creator account: " + permission)
        if request.brand_content_toggle and request.privacy_level == "SELF_ONLY":
            raise ValueError("Branded content cannot use private-only visibility")
        with Session.begin() as db:
            project = db.get(VideoProject, project_id)
            if not project or project.platform != "tiktok":
                raise ValueError("Select a TikTok project")
            artifact, path = approved(db, project)
            if project.target_duration > creator.get("max_video_post_duration_sec", 0):
                raise ValueError("Video exceeds the creator account's duration limit")
            existing = db.scalar(
                select(PlatformPublication).where(
                    PlatformPublication.project_id == project_id,
                    PlatformPublication.platform == "tiktok",
                    PlatformPublication.artifact_hash == artifact.sha256,
                )
            )
            if existing:
                raise ValueError(
                    "This artifact already has a TikTok delivery. Query its status before any new attempt."
                )
            row = PlatformPublication(
                project_id=project_id,
                platform="tiktok",
                artifact_hash=artifact.sha256,
                status="UPLOADING",
                details={"mode": "direct"},
            )
            db.add(row)
            db.flush()
            publication_id = row.id
        try:
            post_info = request.model_dump(exclude={"confirm", "music_usage_confirmed"})
            post_info["is_aigc"] = True
            result = client.init_direct(path, post_info)
            with Session.begin() as db:
                db.get(PlatformPublication, publication_id).remote_id = result["publish_id"]
            client.transfer(path, result["upload_url"])
            with Session.begin() as db:
                db.get(PlatformPublication, publication_id).status = "UPLOADED"
            return publication_id
        except Exception:
            with Session.begin() as db:
                db.get(PlatformPublication, publication_id).status = "NEEDS_RECONCILIATION"
            raise
