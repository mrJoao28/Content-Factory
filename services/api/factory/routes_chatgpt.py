"""Local control routes; OAuth uses its separate, short-lived loopback listener."""

import asyncio
import threading

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from .chatgpt import accounts, login
from .chatgpt_http import ChatGPTError, ChatGPTTransient
from .chatgpt_provider import ChatGPTProvider
from .providers import configured_provider, provider_configuration
from .schemas import AgentResult
from .security import Cancelled, ConfigurationRequired

router = APIRouter()


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str | None = Field(default=None, max_length=200)


class ModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(min_length=1, max_length=200)


class SelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_plan_usage: bool = Field(default=False, strict=True)
    resume: bool = Field(default=False, strict=True)
    expected_selection: dict | None = None


class TestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_plan_usage: bool = Field(default=False, strict=True)


def controlled(action):
    try:
        return action()
    except ChatGPTError as error:
        raise HTTPException(
            409,
            {
                "state": error.state,
                "code": error.code,
                "message": str(error),
                "diagnostic": getattr(error, "diagnostic", None),
            },
        ) from None
    except Cancelled:
        raise HTTPException(409, "Text generation cancelled") from None
    except ChatGPTTransient as error:
        raise HTTPException(
            503, {"message": str(error), "diagnostic": getattr(error, "diagnostic", None)}
        ) from None
    except (ConfigurationRequired, OSError):
        raise HTTPException(
            409, "Secure ChatGPT storage or local listener unavailable. Retry from the same Windows account."
        ) from None


@router.get("/auth/chatgpt")
def status(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {
        **accounts.status(),
        "login": login.status(),
        "provider": configured_provider(),
        "configuration": provider_configuration(),
    }


@router.post("/auth/chatgpt/connect")
def connect(body: LoginRequest):
    return controlled(lambda: login.start(body.account_id))


@router.post("/auth/chatgpt/cancel")
def cancel():
    return login.cancel()


@router.post("/auth/chatgpt/accounts/{account_id}/activate")
def activate(account_id: str):
    controlled(lambda: accounts.activate(account_id))
    return accounts.status()


@router.post("/auth/chatgpt/accounts/{account_id}/disconnect")
def disconnect(account_id: str):
    return controlled(lambda: accounts.disconnect(account_id))


@router.post("/auth/chatgpt/accounts/{account_id}/models")
def models(account_id: str):
    return {"models": controlled(lambda: accounts.catalog(account_id))}


@router.post("/auth/chatgpt/accounts/{account_id}/model")
def model(account_id: str, body: ModelRequest):
    controlled(lambda: accounts.select_model(account_id, body.model))
    return accounts.status()


@router.post("/auth/chatgpt/test")
async def test_connection(body: TestRequest, request: Request):
    if not body.confirm_plan_usage:
        raise HTTPException(400, "Confirm that this test consumes your ChatGPT plan allowance.")

    cancelled = threading.Event()

    def test():
        binding = accounts.binding()
        provider = ChatGPTProvider(accounts, binding)
        provider.generate(
            "Quality Reviewer",
            {"task": "Reply with summary Connection verified and an empty flags array."},
            AgentResult,
            cancel=cancelled.is_set,
        )
        with provider.persistence_guard():
            pass
        generation = provider.generation

        def record(state):
            account = accounts.require_session(state, binding["account_id"], generation)
            account["inference_verified"] = account.get("model") == binding["model"]

        accounts.store.update(record)
        return {"state": "VERIFIED", "account_id": binding["account_id"], "model": binding["model"]}

    async def watch():
        while not cancelled.is_set():
            if await request.is_disconnected():
                cancelled.set()
                raise HTTPException(499, "Text generation cancelled")
            await asyncio.sleep(0.1)

    work = asyncio.create_task(asyncio.to_thread(controlled, test))
    watcher = asyncio.create_task(watch())
    try:
        completed, _ = await asyncio.wait({work, watcher}, return_when=asyncio.FIRST_COMPLETED)
        if watcher in completed:
            return await watcher
        return await work
    finally:
        cancelled.set()
        work.cancel()
        watcher.cancel()
        await asyncio.gather(work, watcher, return_exceptions=True)


@router.post("/projects/{project_id}/text-selection")
def change_job_selection(project_id: str, body: SelectionRequest):
    if not body.confirm_plan_usage:
        raise HTTPException(
            400, "Confirm replacing this job's text connection/model with the current selection."
        )
    from sqlalchemy import select, text

    from .api_helpers import no_running_job, project_or_404, serialize
    from .db import Session
    from .models import JobEvent, ProductionJob, utcnow
    from .providers import job_selection, new_selection, validate_selection
    from .queue import WAITING

    with Session.begin() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        project = project_or_404(db, project_id)
        no_running_job(db, project_id)
        job = db.scalar(
            select(ProductionJob).where(
                ProductionJob.project_id == project.id, ProductionJob.revision == project.revision
            )
        )
        selection = controlled(lambda: validate_selection(new_selection(db)))
        if body.expected_selection is not None and body.expected_selection != selection:
            raise HTTPException(409, "The selected connection/model changed. Review the new selection first.")
        if job and body.resume and job.state == "DRAFT" and job.checkpoint.get("_ai_selection") == selection:
            return serialize(job)
        if not job or job.state not in WAITING:
            raise HTTPException(409, "Only a waiting job can change text selection")
        history = list(job.checkpoint.get("_ai_selection_history", []))
        previous, _ = job_selection(db, job)
        if previous != selection:
            history.append(previous or {"provider": "unresolved"})
        job.checkpoint = {
            **job.checkpoint,
            "_ai_selection": selection,
            "_ai_selection_history": history[-50:],
        }
        if previous != selection:
            db.add(
                JobEvent(
                    project_id=project.id,
                    stage=job.state,
                    message=f"Text selection changed explicitly: {(previous or {}).get('provider', 'unresolved')} -> {selection['provider']}; completed checkpoints retained",
                )
            )
        if body.resume:
            job.checkpoint = {k: v for k, v in job.checkpoint.items() if k != "_failure"}
            job.state, job.error, job.available_at = "DRAFT", None, utcnow()
            job.owner, job.lease_until = None, None
            project.status = "DRAFT"
        return serialize(job)
