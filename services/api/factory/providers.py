"""Provider selection is explicit, persistent and independent from pipeline stages."""

from contextlib import nullcontext
from typing import Protocol

from .config import settings
from .db import Session
from .models import UserSettings
from .security import ConfigurationRequired


class TextProvider(Protocol):
    def generate(self, role, context, response_type, *, emit, cancel): ...
    def persistence_guard(self): ...


def configured_provider(db=None):
    if db is None:
        with Session() as session:
            return configured_provider(session)
    row = db.get(UserSettings, "preferences")
    if row and row.values.get("ai_provider") in {"codex", "chatgpt"}:
        return row.values["ai_provider"]
    # Preserve existing explicit Codex installations. New .env.example selects chatgpt.
    return settings.ai_provider or ("codex" if "codex_provider" in settings.model_fields_set else "chatgpt")


def new_selection(db=None):
    name = configured_provider(db)
    if name == "codex":
        return {"provider": "codex"}
    from .chatgpt import accounts

    try:
        return accounts.binding()
    except ConfigurationRequired:
        status = accounts.status()
        active = next((a for a in status["accounts"] if a["active"]), None)
        return {
            "provider": "chatgpt",
            "account_id": active["id"] if active else None,
            "model": active.get("model") if active else None,
        }


def get_provider(selection) -> TextProvider:
    if selection.get("provider") == "codex":
        return CodexTextProvider()
    if selection.get("provider") != "chatgpt":
        raise ValueError("Unknown text provider")
    from .chatgpt import accounts
    from .chatgpt_provider import ChatGPTProvider

    return ChatGPTProvider(accounts, selection)


class CodexTextProvider:
    def __init__(self):
        from .codex import CodexProvider

        self.provider = CodexProvider()

    def generate(self, *args, **kwargs):
        return self.provider.generate(*args, **kwargs)

    def persistence_guard(self):
        return nullcontext()


def provider_configuration(db=None):
    if db is None:
        with Session() as session:
            return provider_configuration(session)
    row = db.get(UserSettings, "preferences")
    source = (
        "saved_settings"
        if row and row.values.get("ai_provider") in {"codex", "chatgpt"}
        else "environment"
        if settings.ai_provider
        else "legacy_codex_configuration"
        if "codex_provider" in settings.model_fields_set
        else "default"
    )
    return {
        "provider": configured_provider(db),
        "source": source,
        "environment_provider": settings.ai_provider,
        "note": "Saved Settings takes precedence over environment configuration. Existing jobs retain their own selection.",
    }


def job_selection(db, job):
    """Resolve only explicit selection or unambiguous historical execution evidence."""
    from sqlalchemy import func, select

    from .models import JobEvent, ProductionJob

    selection = job.checkpoint.get("_ai_selection")
    if isinstance(selection, dict) and selection.get("provider") in {"codex", "chatgpt"}:
        return selection, "checkpoint"
    if selection is not None:
        return None, "selection_required"
    # Old events lack a job/revision ID: only infer when there is exactly one job.
    count = db.scalar(
        select(func.count()).select_from(ProductionJob).where(ProductionJob.project_id == job.project_id)
    )
    evidence = (
        db.scalar(
            select(JobEvent.id).where(
                JobEvent.project_id == job.project_id,
                JobEvent.created_at >= job.created_at,
                JobEvent.created_at <= job.updated_at,
                JobEvent.message.like("Codex failed;%"),
            )
        )
        if count == 1
        else None
    )
    return ({"provider": "codex"}, "historical_codex_failure") if evidence else (None, "selection_required")


def validate_selection(selection):
    from .chatgpt_http import ChatGPTError

    if not selection:
        raise ChatGPTError(
            "Choose a text provider, connection and model explicitly before resuming.",
            "WAITING_FOR_MODEL",
            "selection_required",
        )
    if selection.get("provider") == "chatgpt":
        from .chatgpt import accounts

        if not selection.get("account_id"):
            raise ChatGPTError(
                "Connect ChatGPT in Settings, then explicitly apply the selected connection to this production."
            )
        if not selection.get("model"):
            raise ChatGPTError(
                "Select a model in Settings, then explicitly apply the selection to this production.",
                "WAITING_FOR_MODEL",
                "model_required",
            )
        accounts.session(selection["account_id"], selection["model"])
    return selection


def job_diagnostics(db, job):
    from sqlalchemy import select

    from .models import JobEvent

    selection, source = job_selection(db, job)
    failure = job.checkpoint.get("_failure", {})
    stage = failure.get("stage")
    if not stage and job.error:
        stage = db.scalar(
            select(JobEvent.stage)
            .where(
                JobEvent.project_id == job.project_id,
                JobEvent.created_at >= job.created_at,
                JobEvent.created_at <= job.updated_at,
                JobEvent.message.like("%: started"),
            )
            .order_by(JobEvent.created_at.desc())
            .limit(1)
        )
    actions = {
        "WAITING_FOR_AUTH": "Reconnect this production's account in Settings, then Resume.",
        "WAITING_FOR_MODEL": "Choose a provider and an available model in Settings, then apply the selection explicitly.",
        "WAITING_FOR_LIMIT": "Check plan usage and resume later; no automatic account or billing switch.",
        "WAITING_FOR_PLATFORM_APPROVAL": "Check granted permissions before reconnecting.",
        "WAITING_FOR_ASSETS": "Check required assets, Piper/voice or imported narration.",
    }
    if failure.get("code") == "invalid_content":
        next_action = "Generated text did not match the required schema. Review the selected model and retry; invalid JSON was not saved."
    elif failure.get("code") == "transient":
        next_action = "The external service is temporarily unavailable. Retry later with the same connection."
    else:
        next_action = actions.get(job.state, "Review the error and text selection before resuming.")
    return {
        "selection": selection,
        "selection_source": source,
        "stage": stage,
        "code": failure.get("code"),
        "global": provider_configuration(db),
        "next_action": next_action,
        "completed_steps": [key for key in job.checkpoint if not key.startswith("_")],
    }
