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
        return {"provider": "chatgpt", "account_id": None, "model": None}


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
