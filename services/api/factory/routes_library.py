import asyncio
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from sqlalchemy import select

from .api_helpers import no_running_job, project_or_404, serialize
from .config import settings
from .db import Session
from .models import Character, ProductionJob, SceneAsset, Series, VideoProject
from .render import probe
from .schemas import AudioMix, CharacterCreate, SeriesCreate
from .security import digest, safe_path

router = APIRouter()


@router.get("/series")
def series_list(channel_id: str | None = None):
    with Session() as db:
        query = select(Series)
        if channel_id:
            query = query.where(Series.channel_id == channel_id)
        return [serialize(x) for x in db.scalars(query)]


@router.post("/series", status_code=201)
def series_create(body: SeriesCreate):
    with Session.begin() as db:
        row = Series(**body.model_dump())
        db.add(row)
        db.flush()
        return serialize(row)


@router.patch("/series/{entity_id}")
def series_update(entity_id: str, body: SeriesCreate):
    with Session.begin() as db:
        row = db.get(Series, entity_id)
        if not row or row.channel_id != body.channel_id:
            raise HTTPException(404, "Series not found in this channel")
        row.name, row.style = body.name, body.style
        return serialize(row)


@router.get("/characters")
def characters():
    with Session() as db:
        return [serialize(x) for x in db.scalars(select(Character))]


def validate_character(db, body):
    if body.series_id and not db.get(Series, body.series_id):
        raise ValueError("Series not found")
    for asset_id in body.expressions.values():
        if not db.get(SceneAsset, asset_id):
            raise ValueError("Expressions must reference imported assets")


@router.post("/characters", status_code=201)
def character_create(body: CharacterCreate):
    with Session.begin() as db:
        validate_character(db, body)
        row = Character(**body.model_dump())
        db.add(row)
        db.flush()
        return serialize(row)


@router.patch("/characters/{entity_id}")
def character_update(entity_id: str, body: CharacterCreate):
    with Session.begin() as db:
        row = db.get(Character, entity_id)
        if not row:
            raise HTTPException(404, "Character not found")
        validate_character(db, body)
        for key, value in body.model_dump().items():
            setattr(row, key, value)
        return serialize(row)


@router.delete("/library/{kind}/{entity_id}")
def library_delete(kind: str, entity_id: str):
    model = {"characters": Character, "series": Series}.get(kind)
    if not model:
        raise HTTPException(404, "Unknown library")
    with Session.begin() as db:
        row = db.get(model, entity_id)
        if not row:
            raise HTTPException(404, "Not found")
        if model is Series:
            if db.scalar(select(Character.id).where(Character.series_id == entity_id)) or db.scalar(
                select(VideoProject.id).where(VideoProject.series_id == entity_id)
            ):
                raise HTTPException(409, "Series is still referenced")
        db.delete(row)
    return {"deleted": True}


async def save_upload(file, directory, suffix):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (str(uuid4()) + suffix)
    total = 0
    try:
        with path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(413, "Upload exceeds configured limit")
                output.write(chunk)
        if not total:
            raise ValueError("Empty upload")
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.get("/assets")
def asset_list():
    with Session() as db:
        return [serialize(x) for x in db.scalars(select(SceneAsset))]


@router.post("/assets", status_code=201)
async def asset_import(file: UploadFile = File(...), license: str = "", kind: str = "prop"):
    if not license.strip() or len(license) > 3000 or kind not in {"character", "background", "prop"}:
        raise ValueError("Provide an asset kind and rights/license declaration")
    if Path(file.filename or "").suffix.lower() != ".png":
        raise ValueError("Only PNG imports are supported; export SVG to PNG first")
    path = await save_upload(file, settings.assets_dir / "imports", ".png")
    try:
        with Image.open(path) as source:
            if source.format != "PNG" or max(source.size) > 4096:
                raise ValueError("Import a valid PNG at most 4096px per side")
            source.verify()
        hashed = digest(path)
        with Session.begin() as db:
            existing = db.scalar(select(SceneAsset).where(SceneAsset.sha256 == hashed))
            if existing:
                path.unlink()
                return serialize(existing)
            row = SceneAsset(
                name=Path(file.filename).stem[:100],
                kind=kind,
                license=license,
                path=str(path.relative_to(settings.assets_dir)),
                sha256=hashed,
            )
            db.add(row)
            db.flush()
            return serialize(row)
    except Exception:
        path.unlink(missing_ok=True)
        raise


@router.get("/assets/{asset_id}/image")
def asset_image(asset_id: str):
    with Session() as db:
        row = db.get(SceneAsset, asset_id)
        if not row or row.kind not in {"character", "background", "prop"}:
            raise HTTPException(404, "Image asset not found")
        return FileResponse(safe_path(settings.assets_dir, row.path), media_type="image/png")


@router.post("/projects/{project_id}/audio")
async def import_audio(project_id: str, file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".wav", ".mp3"}:
        raise ValueError("Import WAV or MP3 narration")
    with Session() as db:
        project_or_404(db, project_id)
        no_running_job(db, project_id)
    path = await save_upload(file, settings.storage_root / "imports", suffix)
    try:
        info = await asyncio.to_thread(probe, path)
        if not any(x["codec_type"] == "audio" for x in info["streams"]):
            raise ValueError("No decodable audio stream")
        with Session.begin() as db:
            project = project_or_404(db, project_id)
            no_running_job(db, project_id)
            project.narration = {
                **project.narration,
                "path": str(path.relative_to(settings.storage_root)),
                "sha256": digest(path),
                "duration": float(info["format"]["duration"]),
            }
            project.approved_hash = None
            project.revision += 1
            project.status = "DRAFT"
            for job in db.scalars(select(ProductionJob).where(ProductionJob.project_id == project_id)):
                if job.state not in {"CANCELLED", "PUBLISHED"}:
                    job.state = "CANCELLED"
        return {"imported": True, "duration": float(info["format"]["duration"])}
    except Exception:
        path.unlink(missing_ok=True)
        raise


@router.post("/assets/audio", status_code=201)
async def audio_asset_import(file: UploadFile = File(...), license: str = "", kind: str = "music"):
    suffix = Path(file.filename or "").suffix.lower()
    if kind not in {"music", "sound-effect"} or not license.strip() or len(license) > 3000:
        raise ValueError("Choose music/sound-effect and declare rights")
    if suffix not in {".wav", ".mp3"}:
        raise ValueError("Import WAV or MP3 audio assets")
    path = await save_upload(file, settings.assets_dir / "imports", suffix)
    try:
        info = await asyncio.to_thread(probe, path)
        if (
            not any(x["codec_type"] == "audio" for x in info["streams"])
            or float(info["format"]["duration"]) > 600
        ):
            raise ValueError("Import decodable audio no longer than 600s")
        hashed = digest(path)
        with Session.begin() as db:
            existing = db.scalar(select(SceneAsset).where(SceneAsset.sha256 == hashed))
            if existing:
                path.unlink()
                return serialize(existing)
            row = SceneAsset(
                name=Path(file.filename).stem[:100],
                kind=kind,
                license=license,
                path=str(path.relative_to(settings.assets_dir)),
                sha256=hashed,
            )
            db.add(row)
            db.flush()
            return serialize(row)
    except Exception:
        path.unlink(missing_ok=True)
        raise


@router.get("/assets/{asset_id}/audio")
def audio_asset_preview(asset_id: str):
    with Session() as db:
        row = db.get(SceneAsset, asset_id)
        if not row or row.kind not in {"music", "sound-effect"}:
            raise HTTPException(404, "Audio asset not found")
        return FileResponse(safe_path(settings.assets_dir, row.path))


@router.patch("/projects/{project_id}/audio-mix")
def configure_audio_mix(project_id: str, body: AudioMix):
    with Session.begin() as db:
        project = project_or_404(db, project_id)
        no_running_job(db, project_id)
        ids = [c.asset_id for c in body.effects] + ([body.music_asset_id] if body.music_asset_id else [])
        for asset_id in ids:
            asset = db.get(SceneAsset, asset_id)
            if not asset or asset.kind not in {"music", "sound-effect"}:
                raise ValueError("Audio mix references an unavailable audio asset")
        if any(cue.time >= project.target_duration for cue in body.effects):
            raise ValueError("Sound effect starts after video end")
        project.narration = {**project.narration, "mix": body.model_dump()}
        project.revision += 1
        project.approved_hash = None
        project.status = "DRAFT"
        for job in db.scalars(select(ProductionJob).where(ProductionJob.project_id == project_id)):
            if job.state not in {"CANCELLED", "PUBLISHED"}:
                job.state = "CANCELLED"
        return serialize(project)


@router.get("/projects/{project_id}/narration")
def narration_preview(project_id: str):
    with Session() as db:
        project = project_or_404(db, project_id)
        if project.narration.get("path"):
            path = safe_path(settings.storage_root, project.narration["path"])
        elif project.narration.get("generated_path"):
            path = Path(project.narration["generated_path"]).resolve()
            if not path.is_relative_to(settings.output_dir) and not path.is_relative_to(
                settings.storage_root
            ):
                raise ValueError("Invalid narration path")
        else:
            raise HTTPException(404, "No narration generated or imported")
        if not path.is_file():
            raise HTTPException(404, "Narration file missing")
        return FileResponse(path)
