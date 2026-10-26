import importlib.util
import json
import shutil
from pathlib import Path

from .codex import auth_status
from .config import settings
from .db import Session
from .render import ffmpeg, ffprobe
from .security import run


def diagnose():
    result = {}
    for name, resolver in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe)):
        try:
            binary = resolver()
            run([binary, "-version"], timeout=10)
            result[name] = {"state": "READY", "path": str(binary)}
        except Exception:
            result[name] = {"state": "UNAVAILABLE", "instructions": "Install FFmpeg including FFprobe"}
    result["codex"] = auth_status()
    result["codex_sdk"] = {
        "state": "READY" if importlib.util.find_spec("openai_codex") else "UNAVAILABLE",
        "note": "Module detection only; actual model access requires a completed turn",
    }
    try:
        import alembic

        result["alembic"] = {"state": "READY", "version": alembic.__version__}
    except ImportError:
        result["alembic"] = {
            "state": "UNAVAILABLE",
            "instructions": "Run setup to install or repair migration dependencies.",
        }
    try:
        from sqlalchemy import text

        with Session() as db:
            mode = db.execute(text("PRAGMA journal_mode")).scalar()
            db.execute(text("SELECT 1"))
        result["database"] = {"state": "READY" if mode == "wal" else "UNAVAILABLE", "journal": mode}
    except Exception:
        result["database"] = {"state": "UNAVAILABLE"}
    for name, path in (("blender", settings.blender_path), ("piper", settings.piper_path)):
        binary = shutil.which(path) if path else None
        try:
            if not binary:
                raise ValueError("missing")
            run([binary, "--version"], timeout=15)
            result[name] = {"state": "READY"}
        except Exception:
            result[name] = {"state": "UNAVAILABLE", "optional": True}
    result["voice"] = {
        "state": "READY"
        if Path(settings.piper_voice_path).is_file() and Path(settings.piper_voice_path + ".json").is_file()
        else "MISSING_CONFIG"
    }
    for name, configured in (
        ("google", settings.google_client_id and settings.google_client_secret),
        ("youtube", settings.google_client_id and settings.google_client_secret),
        ("tiktok", settings.tiktok_client_key and settings.tiktok_client_secret),
    ):
        result[name] = {
            "state": "AUTH_REQUIRED" if configured else "MISSING_CONFIG",
            "note": "Verify live permissions with Verify account after connecting",
        }
    result["publishing"] = {
        "state": "PERMISSION_REQUIRED",
        "note": "Explicit approval and confirmation required",
    }
    return result


if __name__ == "__main__":
    print(json.dumps(diagnose(), indent=2))
