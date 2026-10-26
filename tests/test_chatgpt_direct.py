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
    assert client.post(
        f"/auth/chatgpt/accounts/{account_id}/model", json={"model": "example-model"}
    ).status_code == 200
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
    from factory import chatgpt, pipeline
    from factory.db import Session
    from factory.models import RenderArtifact, ScriptVersion, VideoProject
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
            headers={"Content-Type": "text/event-stream"},
            stream=Fragmented(stream_body(text=result.model_dump_json())),
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        pipeline, "get_provider", lambda selection: ChatGPTProvider(accounts, selection, transport)
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
            doctor = local.get(base + "/doctor").json()
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
