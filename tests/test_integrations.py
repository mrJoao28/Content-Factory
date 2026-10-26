import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from factory.config import settings
from factory.integrations import Google, OAuth, PlatformError, TikTok
from factory.security import ConfigurationRequired, Vault


class MemoryVault:
    """Test-only credential storage; production always uses the OS vault."""

    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def put(self, key, value):
        self.values[key] = dict(value)

    def delete(self, key):
        self.values.pop(key, None)


def setup_oauth(monkeypatch, handler):
    monkeypatch.setattr(settings, "google_client_id", "test-client")
    monkeypatch.setattr(settings, "google_client_secret", "test-secret")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OAuth(client=client, vault=MemoryVault()), client


def test_google_oauth_state_pkce_single_use(monkeypatch):
    def respond(request):
        assert request.url.host == "oauth2.googleapis.com"
        body = parse_qs(request.content.decode())
        assert "code_verifier" in body
        return httpx.Response(
            200,
            json={
                "access_token": "test-access",
                "refresh_token": "test-refresh",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/drive.file",
            },
        )

    oauth, client = setup_oauth(monkeypatch, respond)
    url = oauth.start("google")
    query = parse_qs(urlparse(url).query)
    assert query["scope"] == ["https://www.googleapis.com/auth/drive.file"]
    assert query["code_challenge_method"] == ["S256"]
    state = query["state"][0]
    assert oauth.complete(state, "test-code") == "google"
    assert oauth.token("google") == "test-access"
    with pytest.raises(ValueError):
        oauth.complete(state, "test-code")
    with pytest.raises(ValueError):
        oauth.complete("invalid", "test-code")


def test_token_refresh_and_error_redaction(monkeypatch):
    def respond(request):
        return httpx.Response(200, json={"access_token": "refreshed", "expires_in": 3600})

    oauth, client = setup_oauth(monkeypatch, respond)
    oauth.vault.put("google", {"access_token": "expired", "refresh_token": "test-refresh", "expires_at": 1})
    assert oauth.token("google") == "refreshed"
    google = Google(
        client=httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(403, json={"secret": "never-log"}))
        ),
        oauth=oauth,
    )
    with pytest.raises(PlatformError) as exc:
        google.folders()
    assert "never-log" not in str(exc.value)


def test_drive_resumable_upload_and_folder_reuse(monkeypatch, tmp_path):
    file = tmp_path / "video.mp4"
    file.write_bytes(b"video-test-bytes")
    called = []

    def respond(request):
        called.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"files": [{"id": "existing-folder"}]})
        if request.method == "POST":
            return httpx.Response(200, headers={"Location": "https://www.googleapis.com/upload/session-test"})
        assert request.headers["content-range"] == f"bytes 0-{file.stat().st_size - 1}/{file.stat().st_size}"
        return httpx.Response(
            200, json={"id": "remote-test-id", "webViewLink": "https://drive.google.com/test"}
        )

    oauth, client = setup_oauth(monkeypatch, respond)
    oauth.vault.put("google", {"access_token": "test-access", "expires_at": time.time() + 3600})
    google = Google(client=client, oauth=oauth)
    assert google.folder("AI Content Factory") == "existing-folder"
    assert google.upload(file, {"name": "video.mp4"}, "test-key")["id"] == "remote-test-id"
    assert oauth.vault.get("google")["upload_sessions"]["test-key"].startswith("https://www.googleapis.com/")
    assert len([c for c in called if c.method == "POST"]) == 1


def test_tiktok_inbox_upload_status_and_trusted_urls(monkeypatch, tmp_path):
    calls = []

    def respond(request):
        calls.append(request)
        if request.method == "PUT":
            return httpx.Response(201)
        if "status" in request.url.path:
            return httpx.Response(
                200, json={"error": {"code": "ok"}, "data": {"status": "SEND_TO_USER_INBOX"}}
            )
        return httpx.Response(
            200,
            json={
                "error": {"code": "ok"},
                "data": {
                    "publish_id": "test-id",
                    "upload_url": "https://open-upload.tiktokapis.com/video/test",
                },
            },
        )

    oauth, client = setup_oauth(monkeypatch, respond)
    oauth.vault.put("tiktok", {"access_token": "test-access", "expires_at": time.time() + 3600})
    tiktok = TikTok(client=client, oauth=oauth)
    file = tmp_path / "video.mp4"
    file.write_bytes(b"test-video")
    result = tiktok.init_inbox(file)
    tiktok.transfer(file, result["upload_url"])
    assert tiktok.status(result["publish_id"])["status"] == "SEND_TO_USER_INBOX"
    with pytest.raises(ValueError):
        tiktok.transfer(file, "https://evil.example/video")
    assert any("/inbox/video/init/" in str(c.url) for c in calls)


def test_missing_credentials_are_not_simulated(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "")
    monkeypatch.setattr(settings, "tiktok_client_key", "")
    assert client.post("/auth/google/connect", json={}).status_code == 409
    assert client.post("/auth/tiktok/connect", json={}).status_code == 409
    assert client.get("/connections").json() == []


def test_windows_vault_roundtrip(tmp_path):
    import os

    if os.name != "nt":
        pytest.skip("Windows DPAPI test")
    vault = Vault(tmp_path / "vault")
    try:
        vault.put("google", {"access_token": "test-only-value"})
    except ConfigurationRequired as exc:
        pytest.skip(str(exc))
    assert b"test-only-value" not in (tmp_path / "vault/google.bin").read_bytes()
    assert vault.get("google")["access_token"] == "test-only-value"
    vault.delete("google")
    assert vault.get("google") is None
