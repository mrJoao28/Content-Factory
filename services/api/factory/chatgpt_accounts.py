"""Secure account lifecycle, catalog and serialized token rotation."""

import secrets
import time
from contextlib import contextmanager

import httpx

from .chatgpt_http import RESOURCE, TOKEN, ChatGPTError, ChatGPTTransient, bounded_json
from .chatgpt_identity import IdentityValidator
from .chatgpt_store import ChatGPTStore
from .security import ConfigurationRequired


def account_in(state, account_id):
    return next((a for a in state["accounts"] if a["id"] == account_id), None)


class ChatGPTAccounts:
    def __init__(self, store=None, client=None):
        self.store = store or ChatGPTStore()
        self.client = client or httpx.Client(timeout=15, follow_redirects=False, trust_env=False)
        self.identity = IdentityValidator(self.client)

    def status(self):
        try:
            state = self.store.read()
            accounts = [
                {
                    "id": a["id"],
                    "label": a["label"],
                    "connected": bool(a.get("tokens")) and a.get("auth_state") != "EXPIRED",
                    "active": a["id"] == state.get("active_id"),
                    "model": a.get("model"),
                    "models": a.get("models", []),
                    "inference_verified": bool(a.get("inference_verified")),
                }
                for a in state["accounts"]
            ]
            active = account_in(state, state.get("active_id"))
            status = (
                "EXPIRED"
                if active and active.get("auth_state") == "EXPIRED"
                else "DISCONNECTED"
                if not active or not active.get("tokens")
                else "EXPIRED"
                if active["tokens"]["expires_at"] <= time.time()
                else "CONNECTED"
            )
            return {"state": status, "accounts": accounts, "active_id": state.get("active_id")}
        except Exception:
            return {
                "state": "STORAGE_UNAVAILABLE",
                "accounts": [],
                "active_id": None,
                "message": "Secure credential storage unavailable. Other features remain available.",
            }

    def binding(self):
        state = self.store.read()
        account = account_in(state, state.get("active_id"))
        if not account or not account.get("tokens") or account.get("auth_state") == "EXPIRED":
            raise ChatGPTError("ChatGPT authentication required. Continue with ChatGPT in Settings.")
        if not account.get("model"):
            raise ChatGPTError(
                "Choose a ChatGPT model in Settings before producing text.",
                "WAITING_FOR_MODEL",
                "model_required",
            )
        return {"provider": "chatgpt", "account_id": account["id"], "model": account["model"]}

    def session(self, account_id, model):
        state = self.store.read()
        account = account_in(state, account_id)
        if not account or not account.get("tokens") or state.get("active_id") != account_id:
            raise ChatGPTError(
                "ChatGPT authentication required for this production's original connection. Reconnect and resume."
            )
        if model not in {m["slug"] for m in account.get("models", [])}:
            raise ChatGPTError(
                "Selected model is absent from this account's catalog.",
                "WAITING_FOR_MODEL",
                "model_unavailable",
            )
        return account["generation"]

    def require_session(self, state, account_id, generation):
        account = account_in(state, account_id)
        if (
            state.get("active_id") != account_id
            or not account
            or not account.get("tokens")
            or account["generation"] != generation
            or account.get("auth_state") == "EXPIRED"
        ):
            raise ChatGPTError("ChatGPT connection changed. Reconnect the production's account and resume.")
        return account

    @contextmanager
    def persistence_guard(self, account_id, generation):
        with self.store.locked() as vault:
            state = vault.get("chatgpt") or {"accounts": []}
            self.require_session(state, account_id, generation)
            yield

    def access(self, account_id, generation):
        def renew(state):
            account = self.require_session(state, account_id, generation)
            tokens = account["tokens"]
            if tokens["expires_at"] > time.time() + 90:
                return tokens["access"]
            try:
                response = bounded_json(
                    self.client,
                    "POST",
                    TOKEN,
                    data={
                        "grant_type": "refresh_token",
                        "client_id": account["client_id"],
                        "refresh_token": tokens["refresh"],
                        "resource": RESOURCE,
                    },
                )
                tokens = self.identity.tokens(response, account["client_id"], previous=tokens)
                account["tokens"] = tokens
            except ChatGPTTransient:
                raise
            except ChatGPTError as error:
                # Persist revocation before surfacing the error, without retaining stale credentials.
                account.pop("tokens", None)
                account["auth_state"] = "EXPIRED"
                account["generation"] = secrets.token_hex(16)
                return {"error": str(error), "state": error.state, "code": error.code}
            return tokens["access"]

        token = self.store.update(renew)
        if isinstance(token, dict):
            raise ChatGPTError(token["error"], token["state"], token["code"])
        return token

    def catalog(self, account_id):
        state = self.store.read()
        account = account_in(state, account_id)
        if not account or state.get("active_id") != account_id:
            raise ChatGPTError("Select the account explicitly before refreshing its models.")
        generation = account["generation"]
        token = self.access(account_id, generation)
        value = bounded_json(
            self.client, "GET", RESOURCE + "/models", headers={"Authorization": "Bearer " + token}
        )
        if not isinstance(value.get("models"), list):
            raise ChatGPTError(
                "ChatGPT model catalog was invalid. Refresh it later.", "WAITING_FOR_MODEL", "invalid_catalog"
            )
        models = []
        import re

        for model in value.get("models", [])[:500]:
            if (
                isinstance(model, dict)
                and model.get("visibility") == "list"
                and re.fullmatch(r"[a-zA-Z0-9._:-]{1,200}", str(model.get("slug", "")))
            ):
                models.append(
                    {
                        "slug": model["slug"],
                        "display_name": str(model.get("display_name", model["slug"]))[:200],
                    }
                )

        def save(current):
            current_account = self.require_session(current, account_id, generation)
            current_account["models"] = models
            if current_account.get("model") not in {m["slug"] for m in models}:
                current_account["model"] = None
            return models

        return self.store.update(save)

    def select_model(self, account_id, model):
        def save(state):
            account = account_in(state, account_id)
            if not account or not account.get("tokens") or state.get("active_id") != account_id:
                raise ChatGPTError("ChatGPT authentication required")
            if model not in {m["slug"] for m in account.get("models", [])}:
                raise ValueError("Choose a model from the authenticated catalog")
            account["model"] = model
            account["inference_verified"] = False

        self.store.update(save)

    def activate(self, account_id):
        def save(state):
            selected = account_in(state, account_id)
            if not selected or not selected.get("tokens") or selected.get("auth_state") == "EXPIRED":
                raise ChatGPTError("Reauthorize this saved account before activating it.")
            for account in state["accounts"]:
                account["generation"] = secrets.token_hex(16)
            state["active_id"] = account_id

        self.store.update(save)

    def disconnect(self, account_id):
        # Invalidate generations before attempting remote revocation. No new request can start.
        def detach(state):
            account = account_in(state, account_id)
            if not account:
                raise ValueError("Unknown ChatGPT connection")
            tokens = account.pop("tokens", None)
            account.update(generation=secrets.token_hex(16), inference_verified=False, models=[], model=None)
            if state.get("active_id") == account_id:
                state["active_id"] = None
            return (account["client_id"], tokens)

        client_id, tokens = self.store.update(detach)
        confirmed = False
        if tokens:
            for attempt in range(2):
                try:
                    endpoint = self.identity.metadata()["revocation_endpoint"]
                    bounded_json(
                        self.client,
                        "POST",
                        endpoint,
                        data={
                            "token": tokens["refresh"],
                            "token_type_hint": "refresh_token",
                            "client_id": client_id,
                        },
                    )
                    confirmed = True
                    break
                except ChatGPTTransient:
                    if not attempt:
                        time.sleep(0.5)
                except (ChatGPTError, ConfigurationRequired):
                    break
        return {
            "state": "DISCONNECTED",
            "local_disconnected": True,
            "remote_revocation_confirmed": confirmed,
            "message": "Remote revocation confirmed."
            if confirmed
            else "Disconnected locally; remote revocation was not confirmed. You can disconnect the app in ChatGPT Settings.",
        }

    def mark_expired(self, account_id, generation):
        def mark(state):
            account = account_in(state, account_id)
            if account and account.get("generation") == generation:
                account["auth_state"] = "EXPIRED"
                account["generation"] = secrets.token_hex(16)

        self.store.update(mark)
