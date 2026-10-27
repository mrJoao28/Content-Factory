"""Prepare only isolated browser-test data; never run against an owner's database."""

import os
import sys
import time
from pathlib import Path

from factory.chatgpt_store import ChatGPTStore
from factory.config import settings
from factory.db import Session
from factory.models import JobEvent, ProductionJob, VideoProject, utcnow
from sqlalchemy import select

assert os.environ.get("FACTORY_DISABLE_WORKER") == "1"
assert Path(settings.database_url.removeprefix("sqlite:///")).name.startswith("e2e-")


def seed(state):
    state["active_id"] = "browser-fixture-account"
    state["accounts"] = [
        {
            "id": "browser-fixture-account",
            "label": "Browser test account",
            "generation": "test-session",
            "model": "browser-fixture-model",
            "models": [{"slug": "browser-fixture-model", "display_name": "Browser test model"}],
            "inference_verified": False,
            "tokens": {"access_token": "browser-fixture-not-a-real-token", "expires_at": time.time() + 600},
        }
    ]


ChatGPTStore().update(seed)
with Session.begin() as db:
    job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == sys.argv[1]))
    job.state = "FAILED"
    job.error = "Codex failed; check CLI version, ChatGPT login and usage limits"
    job.checkpoint = {
        "_ai_selection": {"provider": "codex"},
        "creative_director": {"summary": "Retained browser-test checkpoint", "flags": []},
    }
    db.get(VideoProject, sys.argv[1]).status = "FAILED"
    db.add(JobEvent(project_id=sys.argv[1], stage="SCRIPTING", message="Creative Director: started"))

    db.flush()
    job.updated_at = utcnow()

    if "--response-format" in sys.argv:
        job.error = "ChatGPT returned HTML instead of SSE. Check network filtering or service availability."
        response = {
            "http_status": 200,
            "content_type": "text/html",
            "request_id": "req_browser_gateway",
            "format": "html",
            "error_code": "response_contract",
            "message": job.error,
        }
        job.checkpoint = {
            **job.checkpoint,
            "_ai_selection": {
                "provider": "chatgpt",
                "account_id": "browser-fixture-account",
                "model": "browser-fixture-model",
            },
            "_failure": {
                "stage": "SCRIPTING",
                "provider": "chatgpt",
                "code": "response_contract",
                "message": job.error,
                "response": response,
            },
        }
