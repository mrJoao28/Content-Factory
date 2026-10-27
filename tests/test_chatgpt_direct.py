"""Only external OpenAI HTTP is simulated. JWT, callback, vault and SQLite are real."""

import asyncio
import copy
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from factory.chatgpt_accounts import ChatGPTAccounts
from factory.chatgpt_auth import ChatGPTLogin
from factory.chatgpt_http import (
    DISCOVERY,
    ISSUER,
    RESOURCE,
    SCOPES,
    TOKEN,
    ChatGPTError,
    ChatGPTTransient,
)
from factory.chatgpt_provider import ChatGPTProvider
from factory.chatgpt_store import ChatGPTStore
from factory.config import settings
from factory.schemas import AgentResult
from factory.security import Cancelled, ConfigurationRequired, Vault


class TestVault:
    __test__ = False

    def __init__(self):
        self.value = None

    def get(self, name):
        return copy.deepcopy(self.value)

    def put(self, name, value):
        self.value = copy.deepcopy(value)


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class OpenAIHTTP:
    def __init__(self, key):
        self.key = key
        self.nonce = "nonce"
        self.subject = "test-subject"
        self.calls = []
        self.refreshes = 0
        self.scope = SCOPES
        self.model_status = 200
        self.refresh_status = 200
        self.revocation_status = 200
        self.catalog = [{"slug": "example-model", "display_name": "Available model", "visibility": "list"}]

    def token(self, **claims):
        value = {
            "iss": ISSUER,
            "sub": self.subject,
            "aud": "oaiapp_factory_test",
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
            "nonce": self.nonce,
            **claims,
        }
        return jwt.encode(value, self.key, algorithm="RS256", headers={"kid": "test-key"})

    def __call__(self, request):
        self.calls.append((request.method, str(request.url)))
        if str(request.url) == DISCOVERY:
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "token_endpoint": TOKEN,
                    "jwks_uri": ISSUER + "/.well-known/jwks.json",
                    "revocation_endpoint": ISSUER + "/revoke",
                    "id_token_signing_alg_values_supported": ["RS256"],
                },
            )
        if str(request.url).endswith("/.well-known/jwks.json"):
            key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
            return httpx.Response(
                200, json={"keys": [{**key, "kid": "test-key", "use": "sig", "alg": "RS256"}]}
            )
        if str(request.url) == TOKEN:
            form = parse_qs(request.content.decode())
            assert form["client_id"] == ["oaiapp_factory_test"]
            assert form["resource"] == [RESOURCE]
            if form["grant_type"] == ["refresh_token"]:
                self.refreshes += 1
                if self.refresh_status != 200:
                    return httpx.Response(self.refresh_status, json={"error": "invalid_grant"})
                time.sleep(0.05)
                return httpx.Response(
                    200,
                    json={
                        "access_token": "fixture-new-access",
                        "refresh_token": "fixture-rotated-refresh",
                        "token_type": "Bearer",
                        "expires_in": 3600,
                    },
                )
            return httpx.Response(
                200,
                json={
                    "access_token": "fixture-access",
                    "refresh_token": "fixture-refresh",
                    "id_token": self.token(),
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "scope": self.scope,
                },
            )
        if str(request.url) == RESOURCE + "/models":
            assert request.headers["Authorization"].startswith("Bearer fixture-")
            return httpx.Response(self.model_status, json={"models": self.catalog})
        if str(request.url) == ISSUER + "/revoke":
            return httpx.Response(self.revocation_status, content=b"")
        raise AssertionError("Unexpected external endpoint")


@pytest.fixture
def connection(tmp_path, signing_key):
    remote = OpenAIHTTP(signing_key)
    store = ChatGPTStore(TestVault(), tmp_path / "secure")
    accounts = ChatGPTAccounts(store, httpx.Client(transport=httpx.MockTransport(remote), timeout=2))
    login = ChatGPTLogin(accounts)
    yield remote, accounts, login
    login.cancel()
    accounts.client.close()


def authorize(connection):
    remote, accounts, login = connection
    attempt = login.start(open_browser=False)
    pending = login._attempt
    query = parse_qs(urlsplit(attempt["url"]).query)
    remote.nonce = query["nonce"][0]
    callback = (
        pending["redirect"]
        + "?"
        + urlencode(
            {
                "state": query["state"][0],
                "code": "fixture-authorization-code",
                "client_id": "oaiapp_factory_test",
            }
        )
    )
    response = httpx.get(callback, timeout=5)
    assert response.status_code == 200, response.text
    account = accounts.store.read()["accounts"][0]
    accounts.catalog(account["id"])
    accounts.select_model(account["id"], "example-model")
    return account["id"]


def test_dynamic_registration_real_callback_and_safe_status(connection):
    remote, accounts, login = connection
    account_id = authorize(connection)
    state = accounts.store.read()
    assert state["host_id"].startswith("urn:uuid:")
    assert state["accounts"][0]["client_id"] == "oaiapp_factory_test"
    assert login.status()["state"] == "COMPLETE"
    public = json.dumps(accounts.status()) + json.dumps(login.status())
    assert "fixture-access" not in public and "fixture-refresh" not in public and "id_token" not in public
    assert accounts.binding()["account_id"] == account_id
    old_host = state["host_id"]
    returning = login.start(account_id, open_browser=False)
    query = parse_qs(urlsplit(returning["url"]).query)
    assert query["client_id"] == ["oaiapp_factory_test"] and "agent_name_hint" not in query
    assert query["ext_agent_host_id"] == [old_host]
    assert "id_token_hint" not in query


def test_login_through_real_api_routes_reaches_chatgpt_not_platform_oauth(connection, client, monkeypatch):
    from factory import routes_chatgpt
    from factory.chatgpt_http import AUTHORIZE

    remote, accounts, login = connection
    monkeypatch.setattr(routes_chatgpt, "accounts", accounts)
    monkeypatch.setattr(routes_chatgpt, "login", login)
    monkeypatch.setattr("factory.chatgpt_auth.webbrowser.open", lambda *args, **kwargs: False)
    # Exercise the mounted application, not a route stub: platform OAuth has an overlapping path.
    result = client.post("/auth/chatgpt/connect", json={})
    assert result.status_code == 200, result.text
    assert result.json()["state"] == "WAITING"
    query = parse_qs(urlsplit(result.json()["url"]).query)
    assert result.json()["url"].startswith(AUTHORIZE + "?")
    assert query["agent_name_hint"] == ["Content Factory"]
    assert query["client_id"] == ["dynamic_agent_client"]
    remote.nonce = query["nonce"][0]
    response = httpx.get(
        login._attempt["redirect"],
        params={"state": query["state"][0], "code": "fixture-code", "client_id": "oaiapp_factory_test"},
        trust_env=False,
    )
    assert response.status_code == 200
    status = client.get("/auth/chatgpt").json()
    assert status["state"] == "CONNECTED"
    assert status["login"]["state"] == "COMPLETE"
    account_id = status["active_id"]
    assert client.post(f"/auth/chatgpt/accounts/{account_id}/models", json={}).status_code == 200
    assert (
        client.post(f"/auth/chatgpt/accounts/{account_id}/model", json={"model": "example-model"}).status_code
        == 200
    )
    assert client.post("/auth/chatgpt/connect", json={"unknown": True}).status_code == 422
    assert "fixture-access" not in json.dumps(status)


def test_catalog_change_clears_verification_of_removed_model(connection):
    remote, accounts, _ = connection
    account_id = authorize(connection)
    accounts.store.update(lambda state: state["accounts"][0].update(inference_verified=True))
    remote.catalog = []
    accounts.catalog(account_id)
    account = accounts.status()["accounts"][0]
    assert account["model"] is None
    assert account["inference_verified"] is False


@pytest.mark.parametrize("bad", ["state", "host", "path", "duplicate", "method"])
def test_callback_rejects_untrusted_parameters(connection, bad):
    remote, accounts, login = connection
    attempt = login.start(open_browser=False)
    pending = login._attempt
    query = parse_qs(urlsplit(attempt["url"]).query)
    target = (
        pending["redirect"]
        + "?"
        + urlencode({"state": query["state"][0], "code": "fixture-code", "client_id": "oaiapp_factory_test"})
    )
    headers = {}
    if bad == "state":
        target = target.replace(query["state"][0], "wrong")
    if bad == "host":
        headers["Host"] = "localhost:" + str(pending["server"].server_port)
    if bad == "path":
        target = target.replace("/auth/callback", "/callback")
    if bad == "duplicate":
        target += "&code=another"
    response = httpx.request("POST" if bad == "method" else "GET", target, headers=headers, timeout=5)
    assert response.status_code in {400, 405}
    assert not remote.calls
    assert not accounts.store.read()["accounts"]


def test_denial_cancel_timeout_and_no_replacement(connection, monkeypatch):
    remote, accounts, login = connection
    account_id = authorize(connection)
    attempt = login.start(account_id, open_browser=False)
    pending = login._attempt
    query = parse_qs(urlsplit(attempt["url"]).query)
    url = pending["redirect"] + "?" + urlencode({"state": query["state"][0], "error": "access_denied"})
    assert httpx.get(url).status_code == 400
    assert login.status()["state"] == "DENIED"
    assert accounts.binding()["account_id"] == account_id
    first = login.start(account_id, open_browser=False)
    login.cancel()
    assert login.status()["state"] == "CANCELLED"
    monkeypatch.setattr(settings, "chatgpt_login_timeout_seconds", 1)
    login.start(account_id, open_browser=False)
    deadline = time.monotonic() + 3
    while login.status()["state"] == "WAITING" and time.monotonic() < deadline:
        time.sleep(0.05)
    assert login.status()["state"] == "TIMED_OUT"
    assert accounts.binding()["account_id"] == account_id
    assert first["id"] != login.status()["id"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("aud", "another-client"),
        ("nonce", "wrong"),
        ("iss", "https://attacker.test"),
        ("exp", 1),
        ("azp", "another-client"),
    ],
)
def test_jwt_claims_verified(connection, field, value):
    remote, accounts, login = connection
    with pytest.raises(ChatGPTError, match="identity validation"):
        accounts.identity.verify(remote.token(**{field: value}), "oaiapp_factory_test", "nonce")


def test_jwt_signature_and_granted_scopes(connection):
    remote, accounts, login = connection
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(
        {
            "iss": ISSUER,
            "sub": "test",
            "aud": "oaiapp_factory_test",
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
            "nonce": "nonce",
        },
        other,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    with pytest.raises(ChatGPTError):
        accounts.identity.verify(forged, "oaiapp_factory_test", "nonce")
    remote.scope = "openid profile email"
    attempt = login.start(open_browser=False)
    pending = login._attempt
    remote.nonce = parse_qs(urlsplit(attempt["url"]).query)["nonce"][0]
    query = urlencode(
        {
            "state": pending["state_token"],
            "code": "fixture-code",
            "client_id": "oaiapp_factory_test",
            "scope": SCOPES,
        }
    )
    assert httpx.get(pending["redirect"] + "?" + query).status_code == 400
    assert accounts.status()["state"] == "DISCONNECTED"
    assert not accounts.store.read()["accounts"]


def test_refresh_rotation_is_serialized_and_revocation_is_explicit(connection):
    remote, accounts, login = connection
    account_id = authorize(connection)

    def expire(state):
        state["accounts"][0]["tokens"]["expires_at"] = 0

    accounts.store.update(expire)
    generation = accounts.store.read()["accounts"][0]["generation"]
    with ThreadPoolExecutor(2) as pool:
        result = list(pool.map(lambda _: accounts.access(account_id, generation), range(2)))
    assert result == ["fixture-new-access"] * 2 and remote.refreshes == 1
    assert accounts.store.read()["accounts"][0]["tokens"]["refresh"] == "fixture-rotated-refresh"
    disconnected = accounts.disconnect(account_id)
    assert disconnected["local_disconnected"] and disconnected["remote_revocation_confirmed"]
    with pytest.raises(ChatGPTError):
        accounts.access(account_id, generation)
    assert "tokens" not in accounts.store.read()["accounts"][0]


def test_refresh_revoked_and_remote_disconnect_failure(connection):
    remote, accounts, login = connection
    account_id = authorize(connection)

    def expire(state):
        state["accounts"][0]["tokens"]["expires_at"] = 0

    accounts.store.update(expire)
    remote.refresh_status = 400
    generation = accounts.store.read()["accounts"][0]["generation"]
    with pytest.raises(ChatGPTError, match="revoked"):
        accounts.access(account_id, generation)
    assert not accounts.store.read()["accounts"][0].get("tokens")
    remote.refresh_status = 200
    authorize(connection)
    remote.revocation_status = 503
    assert accounts.disconnect(account_id)["remote_revocation_confirmed"] is False


def test_catalog_empty_unavailable_and_invalid_selection(connection):
    remote, accounts, login = connection
    account_id = authorize(connection)
    remote.model_status = 503
    with pytest.raises(ChatGPTTransient):
        accounts.catalog(account_id)
    assert accounts.status()["state"] == "CONNECTED"
    remote.model_status = 200
    remote.catalog = []
    assert accounts.catalog(account_id) == []
    with pytest.raises(ValueError):
        accounts.select_model(account_id, "invented-model")


def test_secure_storage_failure_does_not_require_codex_or_break_api(client, monkeypatch):
    from factory import chatgpt, codex

    monkeypatch.setattr(settings, "ai_provider", "chatgpt")
    monkeypatch.setattr(codex, "executable", lambda: pytest.fail("Direct flow invoked Codex"))

    class Unavailable:
        def read(self):
            raise ConfigurationRequired("secure storage unavailable")

    monkeypatch.setattr(chatgpt.accounts, "store", Unavailable())
    assert client.get("/health").status_code == 200
    assert client.get("/auth/chatgpt").json()["state"] == "STORAGE_UNAVAILABLE"
    assert client.get("/projects").status_code == 200
    assert client.post("/auth/chatgpt/test", json={}).status_code == 400
    assert (
        client.post("/auth/chatgpt/cancel", json={}, headers={"Origin": "https://attacker.test"}).status_code
        == 403
    )


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows DPAPI")
def test_chatgpt_credentials_are_os_encrypted(tmp_path):
    vault = Vault(tmp_path)
    vault.put("chatgpt", {"access": "fixture-access", "refresh": "fixture-refresh"})
    assert b"fixture-access" not in (tmp_path / "chatgpt.bin").read_bytes()
    assert vault.get("chatgpt")["refresh"] == "fixture-refresh"


class Fragmented(httpx.AsyncByteStream):
    def __init__(self, data, delay=0):
        self.data, self.delay = data, delay

    async def __aiter__(self):
        if self.delay:
            await asyncio.sleep(self.delay)
        for i in range(0, len(self.data), 3):
            yield self.data[i : i + 3]


def stream_body(text='{"summary":"A caf\u00e9", "flags":[]}', status="completed", event="response.completed"):
    return (
        "event: response.output_text.delta\r\ndata: "
        + json.dumps({"type": "response.output_text.delta", "delta": "partial"})
        + "\r\n\r\n"
        + "data: "
        + json.dumps(
            {
                "type": event,
                "response": {
                    "status": status,
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": text}],
                        }
                    ],
                },
            },
            ensure_ascii=False,
        )
        + "\r\n\r\n"
    ).encode()


def provider_for(connection, data=None, http_status=200, delay=0):
    _, accounts, _ = connection
    account_id = authorize(connection)

    def handle(request):
        body = json.loads(request.content)
        assert body["store"] is False and body["stream"] is True
        assert set(body) == {"model", "instructions", "input", "store", "stream"}
        assert all(m["role"] != "system" for m in body["input"])
        assert str(request.url) == RESOURCE + "/responses"
        return httpx.Response(
            http_status,
            headers={"Content-Type": "text/event-stream"},
            stream=Fragmented(data if data is not None else stream_body(), delay),
        )

    return ChatGPTProvider(
        accounts,
        {"provider": "chatgpt", "account_id": account_id, "model": "example-model"},
        httpx.MockTransport(handle),
    )


def test_fragmented_sse_completed_json_passes_real_schema(connection):
    provider = provider_for(connection)
    result = provider.generate("Creative Director", {"idea": "A garden"}, AgentResult)
    assert result.summary == "A caf\u00e9"
    assert len(provider.history) == 1


@pytest.mark.parametrize(
    "data",
    [
        b'data: {"type":"response.output_text.delta","delta":"partial"}\n\n',
        stream_body(event="response.incomplete", status="incomplete"),
        stream_body(text="invalid JSON"),
    ],
)
def test_incomplete_eof_and_invalid_json_never_succeed(connection, data):
    provider = provider_for(connection, data)
    # Exhaust transport retries immediately to keep this protocol test fast.
    from factory.security import TransientFailure

    with pytest.raises((ValueError, TransientFailure)):
        provider.generate("Script Writer", {}, AgentResult)
    assert not provider.history


@pytest.mark.parametrize(
    "http_status,state",
    [
        (401, "WAITING_FOR_AUTH"),
        (403, "WAITING_FOR_PLATFORM_APPROVAL"),
        (429, "WAITING_FOR_LIMIT"),
        (404, "WAITING_FOR_MODEL"),
    ],
)
def test_http_failures_have_distinct_recoverable_states(connection, http_status, state):
    provider = provider_for(connection, b"{}", http_status)
    with pytest.raises(ChatGPTError) as raised:
        provider.generate("Quality Reviewer", {}, AgentResult)
    assert raised.value.state == state


def test_stream_plan_limit_is_not_success(connection):
    data = b'data: {"type":"response.failed","response":{"error":{"code":"subscription_sharing_usage_limit_exceeded"}}}\n\n'
    provider = provider_for(connection, data)
    with pytest.raises(ChatGPTError) as raised:
        provider.generate("Quality Reviewer", {}, AgentResult)
    assert raised.value.state == "WAITING_FOR_LIMIT"


def test_cancel_and_disconnect_interrupt_pending_stream(connection):
    provider = provider_for(connection, delay=20)
    cancelled = threading.Event()
    timer = threading.Timer(0.2, cancelled.set)
    timer.start()
    with pytest.raises(Cancelled):
        provider.generate("Creative Director", {}, AgentResult, cancel=cancelled.is_set)
    timer.cancel()
    account_id = provider.selection["account_id"]
    timer = threading.Timer(0.2, lambda: provider.accounts.disconnect(account_id))
    timer.start()
    with pytest.raises(ChatGPTError):
        provider.generate("Creative Director", {}, AgentResult)
    timer.join(timeout=3)
    assert not provider.history


def test_old_callback_replay_and_wrong_client_are_rejected(connection):
    remote, accounts, login = connection
    attempt = login.start(open_browser=False)
    pending = login._attempt
    query = parse_qs(urlsplit(attempt["url"]).query)
    remote.nonce = query["nonce"][0]
    path = "/auth/callback?" + urlencode(
        {"state": query["state"][0], "code": "fixture", "client_id": "oaiapp_factory_test"}
    )
    host = urlsplit(pending["redirect"]).netloc
    assert login.callback(pending, path, host)[0] == 200
    count = len(remote.calls)
    assert login.callback(pending, path, host)[0] == 409
    assert len(remote.calls) == count
    account_id = accounts.store.read()["active_id"]
    login.start(account_id, open_browser=False)
    pending = login._attempt
    path = "/auth/callback?" + urlencode(
        {"state": pending["state_token"], "code": "fixture", "client_id": "different-client"}
    )
    assert login.callback(pending, path, urlsplit(pending["redirect"]).netloc)[0] == 400
    assert accounts.store.read()["active_id"] == account_id


def test_returning_login_rejects_different_identity(connection):
    remote, accounts, login = connection
    account_id = authorize(connection)
    previous = accounts.store.read()["accounts"][0]["tokens"]
    login.start(account_id, open_browser=False)
    pending = login._attempt
    remote.nonce = pending["nonce"]
    remote.subject = "another-user"
    path = "/auth/callback?" + urlencode({"state": pending["state_token"], "code": "fixture"})
    assert login.callback(pending, path, urlsplit(pending["redirect"]).netloc)[0] == 400
    assert accounts.store.read()["accounts"][0]["tokens"] == previous


def test_cancel_during_exchange_never_activates_old_response(connection):
    remote, accounts, login = connection
    entered, release = threading.Event(), threading.Event()

    def handler(request):
        if str(request.url) == TOKEN:
            entered.set()
            assert release.wait(5)
        return remote(request)

    accounts.client = httpx.Client(transport=httpx.MockTransport(handler))
    accounts.identity.client = accounts.client
    login.start(open_browser=False)
    pending = login._attempt
    remote.nonce = pending["nonce"]
    path = "/auth/callback?" + urlencode(
        {"state": pending["state_token"], "code": "fixture", "client_id": "oaiapp_factory_test"}
    )
    results = []
    worker = threading.Thread(
        target=lambda: results.append(login.callback(pending, path, urlsplit(pending["redirect"]).netloc))
    )
    worker.start()
    assert entered.wait(3)
    login.cancel()
    release.set()
    worker.join(timeout=5)
    assert results[0][0] == 409
    assert not accounts.store.read()["accounts"]


def test_json_correction_and_transient_retry_are_bounded(connection):
    remote, accounts, _ = connection
    authorize(connection)
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx.Response(503, headers={"Retry-After": "1"}, json={"error": {"code": "server_error"}})
        content = stream_body(text="not-json") if len(calls) == 2 else stream_body()
        return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, stream=Fragmented(content))

    provider = ChatGPTProvider(accounts, accounts.binding(), httpx.MockTransport(handler))
    assert provider.generate("Script Writer", {}, AgentResult).flags == []
    assert len(calls) == 3
    assert "correction" in json.loads(calls[-1]["input"][0]["content"])


def test_timeout_stops_stream_and_late_error_is_not_success(connection, monkeypatch):
    provider = provider_for(connection, delay=20)
    monkeypatch.setattr(settings, "codex_timeout_seconds", 1)
    started = time.monotonic()
    with pytest.raises(ChatGPTTransient):
        provider.generate("Creative Director", {}, AgentResult)
    assert time.monotonic() - started < 4
    provider = provider_for(
        connection,
        stream_body() + b'data: {"type":"error","code":"subscription_sharing_usage_limit_exceeded"}\n\n',
    )
    with pytest.raises(ChatGPTError):
        provider.generate("Creative Director", {}, AgentResult)
    provider = provider_for(connection, b'data: {"type":"error", "invalid":"\xff"}\n\n')
    with pytest.raises(ValueError, match="UTF-8"):
        provider.generate("Creative Director", {}, AgentResult)


@pytest.mark.parametrize("channel", ["wondernest", "how-it-works"])
def test_direct_pipeline_resume_preserves_completed_steps_and_real_render(
    connection, client, monkeypatch, channel
):
    from factory import chatgpt
    from factory.db import Session
    from factory.models import ProductionJob, RenderArtifact, ScriptVersion, VideoProject
    from factory.queue import Worker
    from factory.schemas import Metadata, Script
    from sqlalchemy import func, select
    from test_render import board, sine

    remote, accounts, login = connection
    authorize(connection)
    monkeypatch.setattr(chatgpt, "accounts", accounts)
    monkeypatch.setattr(settings, "ai_provider", "chatgpt")
    calls = []
    expired_once = False

    def handler(request):
        nonlocal expired_once
        body = json.loads(request.content)
        instructions = body["instructions"]
        role = next(
            role
            for role in [
                "Creative Director",
                "Script Writer",
                "Storyboard Planner",
                "Visual Director",
                "Animation Planner",
                "Quality Reviewer",
                "Publishing Assistant",
            ]
            if role in instructions
        )
        calls.append(role)
        if role == "Script Writer" and not expired_once:
            expired_once = True
            return httpx.Response(401, json={"error": {"code": "token_expired"}})
        if role == "Script Writer":
            result = Script(
                title="An original discovery",
                description="Fixture script",
                beats=["Discover", "Explore", "Share"],
            )
        elif role == "Storyboard Planner":
            result = board()
        elif role == "Publishing Assistant":
            result = Metadata(
                title="An original discovery", description="Fixture metadata", tags=["Original"]
            )
        else:
            result = AgentResult(summary="Reviewed", flags=[])
        return httpx.Response(
            200,
            stream=Fragmented(stream_body(text=result.model_dump_json())),
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original_async_client(**{**kwargs, "transport": transport})
    )
    from factory import codex

    monkeypatch.setattr(
        codex.CodexProvider,
        "generate",
        lambda *args, **kwargs: pytest.fail("Codex forbidden in direct production"),
    )
    created = client.post(
        "/projects",
        json={"idea": "A robot discovers sharing in an original garden " + channel, "channel_id": channel},
    ).json()
    project_id = created["id"]
    sine(settings.storage_root / "voice.wav")
    with Session.begin() as db:
        project = db.get(VideoProject, project_id)
        project.target_duration, project.width, project.height = 2, 160, 284
        project.narration = {"path": "voice.wav"}
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == project_id))
        job.state, job.error = "FAILED", "Codex failed; check CLI version, ChatGPT login and usage limits"
        job.checkpoint = {"_ai_selection": {"provider": "codex"}}
    recovery = client.post(
        f"/projects/{project_id}/text-selection",
        json={"confirm_plan_usage": True, "resume": True, "expected_selection": accounts.binding()},
    )
    assert recovery.status_code == 200, recovery.text
    assert Worker().once()
    detail = client.get(f"/projects/{project_id}").json()
    assert detail["status"] == "WAITING_FOR_AUTH"
    assert "creative_director" in detail["jobs"][0]["checkpoint"]
    authorize(connection)
    assert client.post(f"/projects/{project_id}/jobs/resume", json={}).status_code == 200
    assert Worker().once()
    detail = client.get(f"/projects/{project_id}").json()
    assert detail["status"] == "HUMAN_REVIEW", detail["jobs"]
    assert calls.count("Creative Director") == 1
    assert all(detail["artifacts"][0]["probe"]["checks"].values())
    assert client.get(f"/projects/{project_id}/media/video").status_code == 200
    assert detail["approved_hash"] is None
    assert "fixture-access" not in json.dumps(detail)
    # Simulate a restart after committing the artifact but before the final job checkpoint.
    calls_before_restart = list(calls)
    with Session.begin() as db:
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == project_id))
        job.state = "DRAFT"
        db.get(VideoProject, project_id).status = "DRAFT"
    assert Worker().once()
    assert client.get(f"/projects/{project_id}").json()["status"] == "HUMAN_REVIEW"
    assert calls == calls_before_restart
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(ScriptVersion)) == 1
        assert db.scalar(select(func.count()).select_from(RenderArtifact)) == 1


def test_queue_plan_limit_waits_without_automatic_retry(connection, client, monkeypatch):
    from factory import chatgpt, pipeline
    from factory.db import Session
    from factory.models import ProductionJob
    from factory.queue import Worker
    from sqlalchemy import select

    _, accounts, _ = connection
    authorize(connection)
    monkeypatch.setattr(chatgpt, "accounts", accounts)
    monkeypatch.setattr(settings, "ai_provider", "chatgpt")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"code": "subscription_sharing_usage_limit_exceeded"}})

    monkeypatch.setattr(
        pipeline,
        "get_provider",
        lambda selection: ChatGPTProvider(accounts, selection, httpx.MockTransport(handler)),
    )
    created = client.post(
        "/projects", json={"idea": "An original garden idea with a usage limit", "channel_id": "wondernest"}
    ).json()
    worker = Worker()
    assert worker.once() and not worker.once()
    with Session() as db:
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == created["id"]))
        assert job.state == "WAITING_FOR_LIMIT" and job.attempts == 0
    assert len(calls) == 1


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows DPAPI cross-process storage")
def test_refresh_lock_coordinates_separate_processes(tmp_path):
    import os
    import subprocess
    import sys

    root = tmp_path / "secure-processes"
    root.mkdir()
    vault = Vault(root)
    vault.put(
        "chatgpt",
        {
            "host_id": "urn:uuid:fixture",
            "active_id": "connection",
            "accounts": [
                {
                    "id": "connection",
                    "client_id": "oaiapp_fixture",
                    "subject": "fixture-subject",
                    "generation": "generation",
                    "label": "Fixture",
                    "models": [],
                    "tokens": {
                        "access": "fixture-old-access",
                        "refresh": "fixture-old-refresh",
                        "id_token": "fixture-id",
                        "subject": "fixture-subject",
                        "scopes": SCOPES.split(),
                        "expires_at": 0,
                    },
                }
            ],
        },
    )
    script = tmp_path / "refresh_process.py"
    script.write_text("""
import sys,time,httpx
from pathlib import Path
from factory.chatgpt_accounts import ChatGPTAccounts
from factory.chatgpt_store import ChatGPTStore
from factory.security import Vault
root=Path(sys.argv[1]);counter=Path(sys.argv[2])
def handler(request):
    with counter.open("a") as stream: stream.write("refresh\\n")
    time.sleep(.2)
    return httpx.Response(200,json={"access_token":"fixture-new-access","refresh_token":"fixture-new-refresh","token_type":"Bearer","expires_in":3600})
service=ChatGPTAccounts(ChatGPTStore(Vault(root),root),httpx.Client(transport=httpx.MockTransport(handler)))
assert service.access("connection","generation")=="fixture-new-access"
print("ok")
""")
    from factory.config import ROOT

    env = {**os.environ, "PYTHONPATH": str(ROOT / "services/api")}
    children = [
        subprocess.Popen(
            [sys.executable, str(script), str(root), str(tmp_path / "refresh-count")],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for _ in range(2)
    ]
    try:
        for child in children:
            stdout, stderr = child.communicate(timeout=30)
            assert child.returncode == 0, stderr
            assert stdout.strip() == "ok"
        assert (tmp_path / "refresh-count").read_text().count("refresh") == 1
    finally:
        from factory.security import terminate_tree

        for child in children:
            terminate_tree(child)


def test_api_connection_test_requires_consent_and_validates_real_stream(connection, client, monkeypatch):
    from factory import routes_chatgpt

    _, accounts, login = connection
    authorize(connection)
    monkeypatch.setattr(routes_chatgpt, "accounts", accounts)
    monkeypatch.setattr(routes_chatgpt, "login", login)

    def handler(request):
        return httpx.Response(
            200, headers={"Content-Type": "text/event-stream"}, stream=Fragmented(stream_body())
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        routes_chatgpt,
        "ChatGPTProvider",
        lambda service, binding: ChatGPTProvider(service, binding, transport),
    )
    assert client.post("/auth/chatgpt/test", json={"confirm_plan_usage": False}).status_code == 400
    result = client.post("/auth/chatgpt/test", json={"confirm_plan_usage": True})
    assert result.status_code == 200, result.text
    assert result.json()["state"] == "VERIFIED"
    assert accounts.status()["accounts"][0]["inference_verified"] is True
    assert "fixture-access" not in result.text


def test_explicit_job_selection_preserves_checkpoints(connection, client, monkeypatch):
    from factory import chatgpt
    from factory.db import Session
    from factory.models import ProductionJob
    from sqlalchemy import select

    _, accounts, _ = connection
    authorize(connection)
    monkeypatch.setattr(chatgpt, "accounts", accounts)
    monkeypatch.setattr(settings, "ai_provider", "codex")
    created = client.post(
        "/projects",
        json={"idea": "An explicit provider change for a waiting production", "channel_id": "wondernest"},
    ).json()
    client.post(f"/projects/{created['id']}/jobs/pause", json={})
    with Session.begin() as db:
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == created["id"]))
        job.checkpoint = {**job.checkpoint, "creative_director": {"summary": "Saved checkpoint", "flags": []}}
    monkeypatch.setattr(settings, "ai_provider", "chatgpt")
    assert client.post(f"/projects/{created['id']}/text-selection", json={}).status_code == 400
    response = client.post(f"/projects/{created['id']}/text-selection", json={"confirm_plan_usage": True})
    assert response.status_code == 200, response.text
    saved = response.json()["checkpoint"]
    assert saved["_ai_selection"]["provider"] == "chatgpt"
    assert saved["_ai_selection_history"] == [{"provider": "codex"}]
    assert saved["creative_director"]["summary"] == "Saved checkpoint"
    assert "fixture-access" not in response.text


def test_connection_switch_prevents_stale_result_persistence(connection):
    provider = provider_for(connection)
    result = provider.generate("Creative Director", {}, AgentResult)
    assert result.summary
    state = provider.accounts.store.read()
    account = copy.deepcopy(state["accounts"][0])
    account.update(id="another-connection", client_id="oaiapp_another", label="Different account")
    provider.accounts.store.update(lambda current: current["accounts"].append(account))
    provider.accounts.activate("another-connection")
    with pytest.raises(ChatGPTError):
        with provider.persistence_guard():
            pytest.fail("Stale generation accepted")


def test_real_api_startup_without_codex_dependencies_or_api_key(tmp_path):
    import os
    import socket
    import subprocess
    import sys

    from factory.config import ROOT
    from factory.security import terminate_tree

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    runner = tmp_path / "start_without_codex.py"
    runner.write_text(
        "import sys,uvicorn\nsys.modules['openai_codex']=None\nuvicorn.run('factory.main:app',host='127.0.0.1',port=int(sys.argv[1]),log_level='error',access_log=False)\n"
    )
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "services/api"),
        "AI_PROVIDER": "chatgpt",
        "CODEX_PATH": "content-factory-codex-unavailable",
        "FACTORY_DISABLE_WORKER": "0",
        "DATABASE_URL": "sqlite:///" + str(tmp_path / "live.db"),
        "STORAGE_ROOT": str(tmp_path / "live-data"),
        "OUTPUT_DIR": str(tmp_path / "live-output"),
        "ASSETS_DIR": str(tmp_path / "live-assets"),
    }
    env.pop("OPENAI_API_KEY", None)
    env.pop("CODEX_API_KEY", None)
    process = subprocess.Popen(
        [sys.executable, str(runner), str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
    )
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 30
        with httpx.Client(timeout=2) as local:
            while time.monotonic() < deadline:
                try:
                    if local.get(base + "/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail("Direct API failed to start")
            # Headless Linux may have no secure OS keyring; startup must still work.
            state = local.get(base + "/auth/chatgpt").json()["state"]
            assert state in {"DISCONNECTED", "STORAGE_UNAVAILABLE"}
            # Doctor invokes real local executables; its bounded probes can exceed a 2s HTTP read on Windows.
            doctor = local.get(base + "/doctor", timeout=35).json()
            assert doctor["codex"]["state"] == "OPTIONAL"
            assert doctor["codex_sdk"]["state"] == "UNAVAILABLE"
            project = local.post(
                base + "/projects",
                headers={"X-Factory-Client": "local"},
                json={"idea": "A live startup without Codex or API keys", "channel_id": "wondernest"},
            ).json()
            while time.monotonic() < deadline:
                detail = local.get(base + "/projects/" + project["id"]).json()
                if detail["status"] == "WAITING_FOR_AUTH":
                    break
                time.sleep(0.1)
            assert detail["status"] == "WAITING_FOR_AUTH"
            assert detail["jobs"][0]["checkpoint"]["_ai_selection"]["provider"] == "chatgpt"
    finally:
        terminate_tree(process)


def test_new_project_uses_saved_provider_and_explains_precedence(connection, client, monkeypatch):
    from factory import chatgpt

    _, accounts, _ = connection
    authorize(connection)
    monkeypatch.setattr(chatgpt, "accounts", accounts)
    monkeypatch.setattr(settings, "ai_provider", "codex")
    assert client.patch("/settings", json={"ai_provider": "chatgpt"}).status_code == 200
    project = client.post(
        "/projects", json={"idea": "A fresh explicit provider selection", "channel_id": "wondernest"}
    ).json()
    job = client.get(f"/projects/{project['id']}").json()["jobs"][0]
    assert job["checkpoint"]["_ai_selection"] == accounts.binding()
    assert job["diagnostic"]["global"]["source"] == "saved_settings"
    assert job["diagnostic"]["global"]["environment_provider"] == "codex"


def test_unknown_legacy_selection_never_falls_back_to_codex(client, monkeypatch):
    from factory import codex
    from factory.db import Session
    from factory.models import ProductionJob
    from factory.queue import Worker
    from sqlalchemy import select

    monkeypatch.setattr(
        codex.CodexProvider, "generate", lambda *a, **k: pytest.fail("Implicit Codex execution")
    )
    project = client.post(
        "/projects", json={"idea": "Legacy job without historical evidence", "channel_id": "wondernest"}
    ).json()
    with Session.begin() as db:
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == project["id"]))
        job.checkpoint = {}
    assert Worker().once()
    detail = client.get(f"/projects/{project['id']}").json()
    job = detail["jobs"][0]
    assert job["state"] == "WAITING_FOR_MODEL"
    assert job["diagnostic"]["selection"] is None
    assert job["diagnostic"]["code"] == "selection_required"
    response = client.post(f"/projects/{project['id']}/jobs/resume", json={})
    assert response.status_code == 409


def test_failed_historical_job_explicit_recovery_is_atomic_and_idempotent(connection, client, monkeypatch):
    from factory import chatgpt
    from factory.db import Session
    from factory.models import JobEvent, ProductionJob, VideoProject, utcnow
    from sqlalchemy import select

    _, accounts, _ = connection
    authorize(connection)
    monkeypatch.setattr(chatgpt, "accounts", accounts)
    client.patch("/settings", json={"ai_provider": "chatgpt"})
    project = client.post(
        "/projects", json={"idea": "Recover one historical Codex production", "channel_id": "wondernest"}
    ).json()
    other = client.post(
        "/projects", json={"idea": "Do not alter this other production", "channel_id": "wondernest"}
    ).json()
    old_error = "Codex failed; check CLI version, ChatGPT login and usage limits"
    with Session.begin() as db:
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == project["id"]))
        job.state = "FAILED"
        job.error = old_error
        job.checkpoint = {"creative_director": {"summary": "Already completed", "flags": []}}
        db.add(JobEvent(project_id=project["id"], stage="SCRIPTING", message="Creative Director: started"))
        db.add(JobEvent(project_id=project["id"], stage="FAILED", message=old_error, level="error"))
        db.flush()
        job.updated_at = utcnow()
        db.get(VideoProject, project["id"]).status = "FAILED"
    detail = client.get(f"/projects/{project['id']}").json()
    diagnostic = detail["jobs"][0]["diagnostic"]
    assert diagnostic["selection"] == {"provider": "codex"}
    assert diagnostic["selection_source"] == "historical_codex_failure"
    assert diagnostic["stage"] == "SCRIPTING"
    before_other = client.get(f"/projects/{other['id']}").json()
    endpoint = f"/projects/{project['id']}/text-selection"
    body = {"confirm_plan_usage": True, "resume": True, "expected_selection": accounts.binding()}
    assert (
        client.post(endpoint, json={**body, "expected_selection": {"provider": "codex"}}).status_code == 409
    )
    assert client.get(f"/projects/{project['id']}").json()["jobs"][0]["error"] == old_error
    first = client.post(endpoint, json=body)
    assert first.status_code == 200, first.text
    second = client.post(endpoint, json=body)
    assert second.status_code == 200, second.text
    saved = second.json()
    assert saved["id"] == first.json()["id"]
    assert saved["state"] == "DRAFT" and saved["error"] is None
    assert saved["checkpoint"]["creative_director"]["summary"] == "Already completed"
    assert saved["checkpoint"]["_ai_selection_history"] == [{"provider": "codex"}]
    assert len(client.get(f"/projects/{project['id']}").json()["jobs"]) == 1
    assert client.get(f"/projects/{other['id']}").json() == before_other


def test_recovery_rejects_active_lease_and_upload_before_modifying_job(connection, client, monkeypatch):
    from datetime import timedelta

    from factory import chatgpt
    from factory.db import Session
    from factory.models import PlatformPublication, ProductionJob, utcnow
    from sqlalchemy import select

    _, accounts, _ = connection
    authorize(connection)
    monkeypatch.setattr(chatgpt, "accounts", accounts)
    client.patch("/settings", json={"ai_provider": "chatgpt"})
    project = client.post(
        "/projects", json={"idea": "A leased production must not change", "channel_id": "wondernest"}
    ).json()
    with Session.begin() as db:
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == project["id"]))
        job.state, job.owner, job.lease_until = "FAILED", "other-worker", utcnow() + timedelta(seconds=30)
    endpoint = f"/projects/{project['id']}/text-selection"
    body = {"confirm_plan_usage": True, "resume": True}
    assert client.post(endpoint, json=body).status_code == 409
    with Session.begin() as db:
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == project["id"]))
        job.owner, job.lease_until = None, None
        db.add(
            PlatformPublication(
                project_id=project["id"],
                platform="youtube",
                status="UPLOADING",
                artifact_hash="recovery-test",
            )
        )
    assert client.post(endpoint, json=body).status_code == 409


@pytest.mark.parametrize(
    "missing,expected", [("account", "WAITING_FOR_AUTH"), ("model", "WAITING_FOR_MODEL")]
)
def test_recovery_validation_preserves_previous_error(connection, client, monkeypatch, missing, expected):
    from factory import chatgpt
    from factory.db import Session
    from factory.models import ProductionJob
    from sqlalchemy import select

    _, accounts, _ = connection
    authorize(connection)
    monkeypatch.setattr(chatgpt, "accounts", accounts)
    client.patch("/settings", json={"ai_provider": "chatgpt"})
    project = client.post(
        "/projects",
        json={"idea": "Validate connection before recovery " + missing, "channel_id": "wondernest"},
    ).json()
    with Session.begin() as db:
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == project["id"]))
        job.state, job.error = "FAILED", "Previous failure retained"

    def remove(state):
        if missing == "account":
            state["accounts"] = []
            state["active_id"] = None
        else:
            state["accounts"][0]["model"] = None

    accounts.store.update(remove)
    result = client.post(
        f"/projects/{project['id']}/text-selection", json={"confirm_plan_usage": True, "resume": True}
    )
    assert result.status_code == 409
    assert result.json()["detail"]["state"] == expected
    assert client.get(f"/projects/{project['id']}").json()["jobs"][0]["error"] == "Previous failure retained"


@pytest.mark.parametrize(
    "content_type",
    ["text/event-stream", "", "Text/Event-Stream; charset=UTF-8", " TEXT/EVENT-STREAM ; charset=utf-8"],
)
def test_sse_media_type_is_case_insensitive_without_relaxing_completion(connection, content_type):
    _, accounts, _ = connection
    account_id = authorize(connection)

    def handler(request):
        assert request.headers["Accept"] == "text/event-stream"
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(
            200,
            headers={"Content-Type": content_type, "x-request-id": "req_sse_valid"},
            stream=Fragmented(stream_body()),
        )

    provider = ChatGPTProvider(
        accounts,
        {"provider": "chatgpt", "account_id": account_id, "model": "example-model"},
        httpx.MockTransport(handler),
    )
    assert provider.generate("Creative Director", {}, AgentResult).summary
    assert provider.last_diagnostic["format"] == "sse"
    assert provider.last_diagnostic["request_id"] == "req_sse_valid"


@pytest.mark.parametrize(
    "content_type,payload,kind",
    [
        (
            "application/json",
            b'{"object":"response","status":"completed","output":[{"private":"never log me"}]}',
            "json_completed",
        ),
        ("application/json", b'{"unexpected":"private story"}', "json"),
        ("application/json", b"{broken-json private story", "unknown"),
        ("text/html", b"<html>private login challenge and token</html>", "html"),
        ("text/plain", b"<!DOCTYPE html><html>private gateway response</html>", "html"),
        ("application/json", b"", "empty"),
        ("", b"", "empty"),
        ("application/json", b'data: {"type":"response.completed"}\n\n', "sse_wrong_content_type"),
        ("text/plain", b"private story and secret header copy", "unknown"),
    ],
)
def test_non_sse_success_status_is_classified_never_saved(connection, content_type, payload, kind, caplog):
    _, accounts, _ = connection
    account_id = authorize(connection)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            headers={"Content-Type": content_type, "x-request-id": "req_format_test"},
            stream=Fragmented(payload),
        )

    provider = ChatGPTProvider(
        accounts,
        {"provider": "chatgpt", "account_id": account_id, "model": "example-model"},
        httpx.MockTransport(handler),
    )
    before = accounts.binding()
    with pytest.raises(ChatGPTError) as raised:
        provider.generate("Creative Director", {"private": "private user prompt"}, AgentResult)
    assert raised.value.state == "FAILED"
    safe = raised.value.diagnostic
    assert safe["http_status"] == 200 and safe["format"] == kind
    assert safe["request_id"] == "req_format_test"
    assert len(calls) == 1 and not provider.history
    assert accounts.binding() == before
    combined = caplog.text + str(raised.value) + json.dumps(safe)
    for value in [
        "private story",
        "private user prompt",
        "private login",
        "fixture-access",
        "Authorization",
        "Bearer",
    ]:
        assert value not in combined


@pytest.mark.parametrize(
    "http_status,code,state",
    [
        (200, "subscription_sharing_usage_limit_exceeded", "WAITING_FOR_LIMIT"),
        (200, "model_not_found", "WAITING_FOR_MODEL"),
        (400, "unsupported_parameter", "FAILED"),
        (403, "insufficient_scope", "WAITING_FOR_PLATFORM_APPROVAL"),
    ],
)
def test_json_errors_keep_safe_code_and_request_id_without_private_message(
    connection, http_status, code, state, caplog
):
    _, accounts, _ = connection
    account_id = authorize(connection)
    payload = {
        "error": {
            "code": code,
            "param": "stream",
            "message": "PRIVATE PROMPT fixture-access Bearer secret user@example.com",
        }
    }
    provider = ChatGPTProvider(
        accounts,
        {"provider": "chatgpt", "account_id": account_id, "model": "example-model"},
        httpx.MockTransport(
            lambda request: httpx.Response(
                http_status, headers={"x-request-id": "req_json_error"}, json=payload
            )
        ),
    )
    with pytest.raises(ChatGPTError) as raised:
        provider.generate("Creative Director", {}, AgentResult)
    assert raised.value.state == state
    assert raised.value.diagnostic["format"] == "json_error"
    assert raised.value.diagnostic["error_code"] == code
    assert raised.value.diagnostic["http_status"] == http_status
    assert not provider.history
    assert "PRIVATE" not in caplog.text + str(raised.value)
    if code == "unsupported_parameter":
        assert "parameter stream" in str(raised.value)


def test_untrusted_error_codes_and_headers_are_not_copied_to_diagnostics(connection, caplog):
    _, accounts, _ = connection
    account_id = authorize(connection)

    def handler(request):
        return httpx.Response(
            400,
            headers={
                "x-request-id": "Bearer fixture-access",
                "Content-Type": "application/json; secret=fixture-access",
            },
            json={"error": {"code": ["private"], "message": "private", "param": "private"}},
        )

    provider = ChatGPTProvider(
        accounts,
        {"provider": "chatgpt", "account_id": account_id, "model": "example-model"},
        httpx.MockTransport(handler),
    )
    with pytest.raises(ChatGPTError) as raised:
        provider.generate("Creative Director", {}, AgentResult)
    assert raised.value.diagnostic["request_id"] is None
    assert raised.value.diagnostic["error_code"] == "unrecognized_error"
    assert "fixture-access" not in caplog.text + str(raised.value)
    assert "private" not in caplog.text.replace("private server message omitted", "")


def test_real_routes_persist_safe_transport_diagnostic_and_preserve_job(
    connection, client, monkeypatch, caplog
):
    from factory import chatgpt
    from factory.db import Session
    from factory.models import ProductionJob
    from factory.queue import Worker
    from sqlalchemy import select

    _, accounts, _ = connection
    authorize(connection)
    monkeypatch.setattr(chatgpt, "accounts", accounts)
    monkeypatch.setattr(settings, "ai_provider", "chatgpt")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "text/html", "x-request-id": "req_gateway"},
            text="<html>PRIVATE CHALLENGE fixture-access</html>",
        )
    )
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(**{**kwargs, "transport": transport}))
    project = client.post(
        "/projects",
        json={"idea": "A private idea must never enter transport diagnostics", "channel_id": "wondernest"},
    ).json()
    with Session.begin() as db:
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == project["id"]))
        job.checkpoint = {**job.checkpoint, "creative_director": {"summary": "Saved earlier", "flags": []}}
        selection = job.checkpoint["_ai_selection"]
    assert Worker().once()
    detail = client.get(f"/projects/{project['id']}").json()
    saved = detail["jobs"][0]
    assert saved["state"] == "FAILED" and saved["checkpoint"]["_ai_selection"] == selection
    assert saved["checkpoint"]["creative_director"]["summary"] == "Saved earlier"
    assert saved["diagnostic"]["stage"] == "SCRIPTING"
    assert saved["diagnostic"]["response"]["format"] == "html"
    assert saved["diagnostic"]["response"]["request_id"] == "req_gateway"
    assert not detail["artifacts"]
    assert "PRIVATE CHALLENGE" not in json.dumps(detail) + caplog.text
    assert "fixture-access" not in json.dumps(detail) + caplog.text


@pytest.mark.parametrize(
    "http_status,payload,content_type,state",
    [
        (401, b"<html>PRIVATE</html>", "text/html", "WAITING_FOR_AUTH"),
        (403, b"<html>PRIVATE</html>", "text/html", "WAITING_FOR_PLATFORM_APPROVAL"),
        (429, b"", "application/json", "WAITING_FOR_LIMIT"),
    ],
)
def test_non_json_http_errors_keep_status_semantics(connection, http_status, payload, content_type, state):
    _, accounts, _ = connection
    account_id = authorize(connection)
    provider = ChatGPTProvider(
        accounts,
        {"provider": "chatgpt", "account_id": account_id, "model": "example-model"},
        httpx.MockTransport(
            lambda request: httpx.Response(
                http_status,
                headers={"Content-Type": content_type, "x-request-id": "req_http_error"},
                content=payload,
            )
        ),
    )
    with pytest.raises(ChatGPTError) as raised:
        provider.generate("Creative Director", {}, AgentResult)
    assert raised.value.state == state
    assert raised.value.diagnostic["http_status"] == http_status
    assert raised.value.diagnostic["format"] == ("html" if payload else "empty")
    assert "PRIVATE" not in str(raised.value)


def test_connection_test_real_route_returns_safe_response_metadata(connection, client, monkeypatch):
    from factory import routes_chatgpt

    _, accounts, _ = connection
    authorize(connection)
    monkeypatch.setattr(routes_chatgpt, "accounts", accounts)
    original = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"x-request-id": "req_test_connection"},
            json={
                "error": {
                    "code": "unsupported_parameter",
                    "param": "stream",
                    "message": "PRIVATE PROMPT fixture-access",
                }
            },
        )
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(**{**kwargs, "transport": transport}))
    response = client.post("/auth/chatgpt/test", json={"confirm_plan_usage": True})
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["state"] == "FAILED"
    assert detail["diagnostic"]["format"] == "json_error"
    assert detail["diagnostic"]["request_id"] == "req_test_connection"
    assert "parameter stream" in detail["message"]
    assert "PRIVATE" not in response.text and "fixture-access" not in response.text
    assert not accounts.status()["accounts"][0]["inference_verified"]


@pytest.mark.parametrize(
    "payload,kind",
    [
        (b'{"error":{"code":"model_not_found","message":"PRIVATE"}}', "json_error"),
        (b'{"object":"response","status":"completed","output":[]}', "json_completed"),
        (b"<html>PRIVATE gateway page</html>", "html"),
    ],
)
def test_missing_content_type_does_not_accept_non_sse(connection, payload, kind):
    _, accounts, _ = connection
    account_id = authorize(connection)
    provider = ChatGPTProvider(
        accounts,
        {"provider": "chatgpt", "account_id": account_id, "model": "example-model"},
        httpx.MockTransport(lambda request: httpx.Response(200, stream=Fragmented(payload))),
    )
    with pytest.raises(ChatGPTError) as raised:
        provider.generate("Creative Director", {}, AgentResult)
    assert raised.value.diagnostic["content_type"] == "missing"
    assert raised.value.diagnostic["format"] == kind
    assert not provider.history
    assert "PRIVATE" not in str(raised.value)


def test_missing_content_type_requires_completed_event_and_real_json_schema(connection):
    _, accounts, _ = connection
    account_id = authorize(connection)
    selection = {"provider": "chatgpt", "account_id": account_id, "model": "example-model"}
    partial = b'data: {"type":"response.output_text.delta","delta":"PRIVATE partial"}\n\n'
    provider = ChatGPTProvider(
        accounts,
        selection,
        httpx.MockTransport(lambda request: httpx.Response(200, stream=Fragmented(partial))),
    )
    from factory.chatgpt_http import ChatGPTTransient

    with pytest.raises(ChatGPTTransient) as raised:
        asyncio.run(provider._stream({}, "fixture-bearer", lambda kind: None))
    assert raised.value.diagnostic["error_code"] == "missing_completion"
    assert not provider.history
    invalid = ChatGPTProvider(
        accounts,
        selection,
        httpx.MockTransport(
            lambda request: httpx.Response(200, stream=Fragmented(stream_body(text="PRIVATE invalid JSON")))
        ),
    )
    with pytest.raises(ValueError) as raised:
        invalid.generate("Creative Director", {}, AgentResult)
    assert raised.value.diagnostic["error_code"] == "invalid_content"
    assert "PRIVATE" not in str(raised.value)
    assert not invalid.history


def test_missing_content_type_valid_sse_bom_and_fragmented_unicode(connection):
    _, accounts, _ = connection
    account_id = authorize(connection)
    content = b"\xef\xbb\xbf" + b": keepalive\r\n\r\n" + stream_body()
    provider = ChatGPTProvider(
        accounts,
        {"provider": "chatgpt", "account_id": account_id, "model": "example-model"},
        httpx.MockTransport(lambda request: httpx.Response(200, stream=Fragmented(content))),
    )
    assert provider.generate("Creative Director", {}, AgentResult).summary == "A caf\u00e9"
    assert provider.last_diagnostic["content_type"] == "missing"
    assert provider.last_diagnostic["format"] == "sse"


@pytest.mark.parametrize("source", ["delta", "text_done", "item_done", "all"])
def test_empty_terminal_output_uses_streamed_text_only_after_completed(connection, source):
    _, accounts, _ = connection
    account_id = authorize(connection)
    text = AgentResult(summary="Completed stream", flags=[]).model_dump_json()
    events = []
    if source in {"delta", "all"}:
        events += [
            {"type": "response.output_text.delta", "output_index": 0, "content_index": 0, "delta": text[:8]},
            {"type": "response.output_text.delta", "output_index": 0, "content_index": 0, "delta": text[8:]},
        ]
    if source in {"text_done", "all"}:
        events.append(
            {"type": "response.output_text.done", "output_index": 0, "content_index": 0, "text": text}
        )
    if source in {"item_done", "all"}:
        events.append(
            {
                "type": "response.output_item.done",
                "output_index": 0,
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": text}],
                },
            }
        )
    events.append({"type": "response.completed", "response": {"status": "completed", "output": []}})
    body = b"".join(("data: " + json.dumps(event) + "\n\n").encode() for event in events)
    provider = ChatGPTProvider(
        accounts,
        {"provider": "chatgpt", "account_id": account_id, "model": "example-model"},
        httpx.MockTransport(lambda request: httpx.Response(200, stream=Fragmented(body))),
    )
    assert provider.generate("Creative Director", {}, AgentResult).summary == "Completed stream"
    assert provider.last_diagnostic["format"] == "sse"
    assert provider.last_diagnostic["content_type"] == "missing"
    assert len(provider.history) == 1


@pytest.mark.parametrize("outcome", ["eof", "incomplete", "failed", "refusal", "empty", "invalid_json"])
def test_streamed_text_never_bypasses_completion_errors_or_schema(connection, outcome):
    from factory.chatgpt_http import ChatGPTTransient

    _, accounts, _ = connection
    account_id = authorize(connection)
    text = (
        AgentResult(summary="PRIVATE streamed content", flags=[]).model_dump_json()
        if outcome != "invalid_json"
        else "PRIVATE invalid JSON"
    )
    events = [] if outcome == "empty" else [{"type": "response.output_text.delta", "delta": text}]
    if outcome == "incomplete":
        events.append({"type": "response.incomplete", "response": {"status": "incomplete"}})
    elif outcome == "failed":
        events.append(
            {
                "type": "response.failed",
                "response": {"error": {"code": "subscription_sharing_usage_limit_exceeded"}},
            }
        )
    elif outcome == "refusal":
        events.append({"type": "response.refusal.done", "refusal": "PRIVATE refusal"})
    if outcome != "eof":
        events.append({"type": "response.completed", "response": {"status": "completed", "output": []}})
    body = b"".join(("data: " + json.dumps(event) + "\n\n").encode() for event in events)
    provider = ChatGPTProvider(
        accounts,
        {"provider": "chatgpt", "account_id": account_id, "model": "example-model"},
        httpx.MockTransport(lambda request: httpx.Response(200, stream=Fragmented(body))),
    )
    with pytest.raises((ValueError, ChatGPTError, ChatGPTTransient)) as raised:
        if outcome == "invalid_json":
            provider.generate("Creative Director", {}, AgentResult)
        else:
            asyncio.run(provider._stream({}, "fixture-bearer", lambda kind: None))
    assert "PRIVATE" not in str(raised.value)
    assert not provider.history
    if outcome == "empty":
        assert "delta_events=0" in str(raised.value)


def test_storyboard_retry_keeps_script_checkpoints_and_renders_35_seconds(connection, client, monkeypatch):
    from factory import chatgpt, codex
    from factory.db import Session
    from factory.models import ProductionJob, ScriptVersion, VideoProject
    from factory.queue import Worker
    from factory.schemas import Metadata, Script
    from sqlalchemy import func, select
    from test_chatgpt_limits import BytesStream, representative_board, representative_stream
    from test_render import sine

    _, accounts, _ = connection
    authorize(connection)
    monkeypatch.setattr(chatgpt, "accounts", accounts)
    monkeypatch.setattr(settings, "ai_provider", "chatgpt")
    monkeypatch.setattr(
        codex.CodexProvider, "generate", lambda *args, **kwargs: pytest.fail("Codex forbidden")
    )
    board = representative_board()
    compact = json.dumps(board.model_dump(exclude_defaults=True), separators=(",", ":"))
    payload = representative_stream(compact)
    calls = []

    def handler(request):
        body = json.loads(request.content)
        instructions = body["instructions"]
        assert body["stream"] is True and body["store"] is False
        assert "compact JSON" in instructions
        prompt = json.loads(body["input"][0]["content"])
        role = next(
            role
            for role in [
                "Creative Director",
                "Script Writer",
                "Storyboard Planner",
                "Visual Director",
                "Animation Planner",
                "Quality Reviewer",
                "Publishing Assistant",
            ]
            if role in instructions
        )
        calls.append(role)
        assert role not in {"Creative Director", "Script Writer"}
        if role == "Storyboard Planner":
            limits = prompt["generation_limits"]
            assert limits["max_scenes"] == 7 and limits["target_duration_seconds"] == 35
            assert (
                prompt["required_json_schema"]["$defs"]["Layer"]["properties"]["keyframes"]["maxItems"] == 6
            )
            return httpx.Response(200, stream=BytesStream(payload))
        result = (
            Metadata(title="A safe discovery", description="Fixture", tags=["Original"])
            if role == "Publishing Assistant"
            else AgentResult(summary="Reviewed", flags=[])
        )
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=Fragmented(stream_body(text=result.model_dump_json())),
        )

    original = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(**{**kwargs, "transport": transport}))
    created = client.post(
        "/projects",
        json={"idea": "Seven scenes in a 35 second original garden adventure", "channel_id": "wondernest"},
    ).json()
    pid = created["id"]
    script = Script(
        title="A safe discovery", description="Fixture script", beats=["Explore", "Share"]
    ).model_dump(mode="json")
    director = AgentResult(summary="Saved director checkpoint", flags=[]).model_dump(mode="json")
    sine(settings.storage_root / "voice35.wav", seconds=35)
    with Session.begin() as db:
        project = db.get(VideoProject, pid)
        project.width, project.height = 160, 284
        project.narration = {"path": "voice35.wav"}
        job = db.scalar(select(ProductionJob).where(ProductionJob.project_id == pid))
        job.checkpoint = {**job.checkpoint, "creative_director": director, "script_writer": script}
        job_id = job.id
    monkeypatch.setattr(settings, "chatgpt_stream_max_bytes", 2_000_000)
    assert Worker().once()
    failed = client.get(f"/projects/{pid}").json()
    assert failed["status"] == "FAILED"
    assert failed["jobs"][0]["diagnostic"]["code"] == "stream_limit"
    assert "storyboard_planner" not in failed["jobs"][0]["checkpoint"]
    assert failed["jobs"][0]["checkpoint"]["script_writer"] == script
    monkeypatch.setattr(settings, "chatgpt_stream_max_bytes", 16_777_216)
    assert client.post(f"/projects/{pid}/jobs/resume", json={}).status_code == 200
    assert Worker().once()
    detail = client.get(f"/projects/{pid}").json()
    assert detail["status"] == "HUMAN_REVIEW", detail["jobs"]
    assert len(detail["jobs"]) == 1 and detail["jobs"][0]["id"] == job_id and detail["revision"] == 1
    cp = detail["jobs"][0]["checkpoint"]
    assert cp["creative_director"] == director and cp["script_writer"] == script
    assert sum(scene["duration"] for scene in cp["storyboard_planner"]["scenes"]) == 35
    assert calls.count("Storyboard Planner") == 2
    assert all(detail["artifacts"][0]["probe"]["checks"].values())
    assert len(detail["artifacts"]) == 1 and detail["approved_hash"] is None
    assert client.get(f"/projects/{pid}/media/video").status_code == 200
    with Session() as db:
        assert (
            db.scalar(select(func.count()).select_from(ScriptVersion).where(ScriptVersion.project_id == pid))
            == 1
        )


@pytest.mark.parametrize("failure", ["layers", "keyframes", "duration"])
def test_generated_storyboard_limits_are_validated_then_corrected(connection, monkeypatch, failure):
    from factory.schemas import Board
    from test_chatgpt_limits import BytesStream, event, representative_board

    _, accounts, _ = connection
    account_id = authorize(connection)
    valid = representative_board().model_dump(exclude_defaults=True)
    import copy

    invalid = copy.deepcopy(valid)
    if failure == "layers":
        invalid["scenes"][0]["layers"].append(copy.deepcopy(invalid["scenes"][0]["layers"][0]))
    elif failure == "keyframes":
        invalid["scenes"][0]["layers"][0]["keyframes"].append({"time": 5.1})
    else:
        invalid["scenes"][0]["duration"] = 4
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        text = json.dumps(invalid if len(calls) == 1 else valid, separators=(",", ":"))
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=BytesStream(
                event(
                    {
                        "type": "response.completed",
                        "response": {
                            "status": "completed",
                            "output": [
                                {
                                    "type": "message",
                                    "role": "assistant",
                                    "content": [{"type": "output_text", "text": text}],
                                }
                            ],
                        },
                    }
                )
            ),
        )

    provider = ChatGPTProvider(
        accounts,
        {"provider": "chatgpt", "account_id": account_id, "model": "example-model"},
        httpx.MockTransport(handler),
    )
    result = provider.generate("Storyboard Planner", {"duration": 35}, Board)
    assert len(calls) == 2 and sum(s.duration for s in result.scenes) == 35
    assert "correction" in json.loads(calls[1]["input"][0]["content"])


def test_many_event_stream_cancellation_does_not_save_partial_board(connection):
    from factory.schemas import Board
    from factory.security import Cancelled
    from test_chatgpt_limits import BytesStream, representative_board, representative_stream

    _, accounts, _ = connection
    account_id = authorize(connection)
    payload = representative_stream(
        json.dumps(representative_board().model_dump(exclude_defaults=True), separators=(",", ":"))
    )
    provider = ChatGPTProvider(
        accounts,
        {"provider": "chatgpt", "account_id": account_id, "model": "example-model"},
        httpx.MockTransport(lambda request: httpx.Response(200, stream=BytesStream(payload))),
    )
    cancelled = threading.Event()
    with pytest.raises(Cancelled):
        provider.generate(
            "Storyboard Planner",
            {"duration": 35},
            Board,
            emit=lambda kind: cancelled.set(),
            cancel=cancelled.is_set,
        )
    assert not provider.history


def test_direct_timeout_setting_overrides_compatibility_timeout(connection, monkeypatch):
    from factory.chatgpt_limits import StreamTimeout

    monkeypatch.setattr(settings, "chatgpt_timeout_seconds", 0.15)
    monkeypatch.setattr(settings, "codex_timeout_seconds", 300)
    provider = provider_for(connection, delay=2)
    with pytest.raises(StreamTimeout):
        provider.generate("Creative Director", {}, AgentResult)
    assert not provider.history


def test_many_event_storyboard_eof_never_saves_partial_result(connection):
    from factory.chatgpt_http import ChatGPTTransient
    from test_chatgpt_limits import BytesStream, representative_board, representative_stream

    _, accounts, _ = connection
    account_id = authorize(connection)
    payload = representative_stream(
        json.dumps(representative_board().model_dump(exclude_defaults=True), separators=(",", ":"))
    )
    payload = payload[: payload.rfind(b'data: {"type":"response.completed"')]
    provider = ChatGPTProvider(
        accounts,
        {"provider": "chatgpt", "account_id": account_id, "model": "example-model"},
        httpx.MockTransport(lambda request: httpx.Response(200, stream=BytesStream(payload))),
    )
    with pytest.raises(ChatGPTTransient) as raised:
        asyncio.run(provider._stream({}, "fixture-bearer", lambda kind: None))
    assert raised.value.diagnostic["error_code"] == "missing_completion"
    assert provider.stream_budget.traffic > 2_000_000
    assert not provider.history


def test_stream_traffic_budget_is_shared_across_json_repair_requests(connection, monkeypatch):
    from factory.chatgpt_limits import StreamLimitExceeded

    _, accounts, _ = connection
    account_id = authorize(connection)
    invalid, valid = stream_body(text="not-json"), stream_body()
    monkeypatch.setattr(settings, "chatgpt_stream_max_bytes", len(invalid) + len(valid) - 1)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=Fragmented(invalid if len(calls) == 1 else valid),
        )

    provider = ChatGPTProvider(
        accounts,
        {"provider": "chatgpt", "account_id": account_id, "model": "example-model"},
        httpx.MockTransport(handler),
    )
    with pytest.raises(StreamLimitExceeded) as raised:
        provider.generate("Creative Director", {}, AgentResult)
    assert len(calls) == 2 and raised.value.code == "stream_limit"
    assert not provider.history
