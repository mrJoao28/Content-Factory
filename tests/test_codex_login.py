import io
import subprocess
import sys
import threading

import pytest
from factory import codex
from factory.codex_auth import LoginManager
from factory.codex_auth_bridge import official_url


def manager(monkeypatch, state="AUTH_REQUIRED"):
    value = LoginManager()
    monkeypatch.setattr(value, "_verify", lambda: {"state": state})
    return value


def test_existing_chatgpt_login_is_reused_without_process(monkeypatch):
    value = manager(monkeypatch, "READY")
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("Already logged in"))
    assert value.start()["state"] == "READY"


def test_pending_login_is_idempotent_and_cancelled_without_logout(monkeypatch):
    value = manager(monkeypatch)
    value._state = {"state": "LOGIN_PENDING", "url": "https://auth.openai.com/login"}
    import time

    value._started = value._checked = time.monotonic()
    assert value.start() == value._state
    assert value.cancel()["state"] == "CANCELLED"
    assert value._process is None


def test_saved_session_completes_stuck_login(monkeypatch):
    value = manager(monkeypatch, "READY")
    value._state = {"state": "LOGIN_PENDING"}
    import time

    value._started = time.monotonic()
    assert value.status()["state"] == "READY"


def test_login_timeout_cleans_up_owned_process(monkeypatch):
    value = manager(monkeypatch)
    value._state = {"state": "LOGIN_PENDING"}
    process = object()
    value._process = process
    stopped = []
    monkeypatch.setattr("factory.codex_auth.terminate_tree", stopped.append)
    assert value.status()["state"] == "TIMED_OUT"
    assert stopped == [process]
    assert value._process is None


def test_cli_timeout_and_missing_runtime_have_accurate_states(monkeypatch):
    monkeypatch.setattr(codex, "executable", lambda: ["codex"])

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("codex", 10)

    monkeypatch.setattr(subprocess, "run", timeout)
    assert codex.cli_auth_status()["state"] == "UNAVAILABLE"
    from factory.security import ConfigurationRequired

    def unavailable():
        raise ConfigurationRequired("missing")

    monkeypatch.setattr(codex, "executable", unavailable)
    assert codex.cli_auth_status()["state"] == "UNAVAILABLE"


def test_cli_auth_only_accepts_successful_chatgpt_login(monkeypatch):
    monkeypatch.setattr(codex, "executable", lambda: ["codex"])
    for code, message, expected in [
        (0, b"Logged in using ChatGPT", "READY"),
        (0, b"Logged in using an API key", "AUTH_REQUIRED"),
        (1, b"Not logged in", "AUTH_REQUIRED"),
    ]:
        monkeypatch.setattr(
            subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], code, b"", message)
        )
        assert codex.cli_auth_status()["state"] == expected


def test_login_helper_failure_does_not_expose_raw_output(monkeypatch):
    value = manager(monkeypatch)
    value._state = {"state": "STARTING"}

    class Process:
        stdout = io.StringIO('{"state":"FAILED","instructions":"Retry official login","secret":"private"}\n')

        def wait(self, timeout):
            return 1

    value._process = Process()
    monkeypatch.setattr("factory.codex_auth.terminate_tree", lambda p: None)
    value._read(value._process, value._generation)
    assert value._state == {"state": "FAILED", "instructions": "Retry official login"}


def test_auth_challenge_urls_must_be_official_https():
    assert official_url("https://auth.openai.com/authorize?state=challenge")
    for url in ("http://auth.openai.com/", "https://openai.com.attacker.test/", "javascript:alert(1)"):
        with pytest.raises(ValueError):
            official_url(url)


def test_login_subprocess_returns_challenge_then_verifies_cli(monkeypatch, tmp_path):
    value = manager(monkeypatch)
    fixture = tmp_path / "login_fixture.py"
    fixture.write_text(
        'import json,time\nprint(json.dumps({"state":"LOGIN_PENDING","url":"https://auth.openai.com/login"}),flush=True)\ntime.sleep(20)\n'
    )
    original = subprocess.Popen
    started = threading.Event()

    def spawn(args, **kwargs):
        proc = original(
            [sys.executable, str(fixture)] if "factory.codex_auth_bridge" in args else args, **kwargs
        )
        started.set()
        return proc

    monkeypatch.setattr(subprocess, "Popen", spawn)
    try:
        assert value.start()["state"] == "STARTING"
        assert started.wait(2)
        import time

        deadline = time.monotonic() + 5
        while value._state["state"] == "STARTING" and time.monotonic() < deadline:
            time.sleep(0.02)
        assert value._state["url"] == "https://auth.openai.com/login"
        monkeypatch.setattr(value, "_verify", lambda: {"state": "READY"})
        value._checked = 0
        assert value.status() == {"state": "READY"}
    finally:
        value.cancel()


def test_official_sdk_login_uses_its_matching_runtime(monkeypatch):
    import types

    from factory import codex_auth_bridge

    configurations = []
    emitted = []

    class Config:
        def __init__(self, **kwargs):
            configurations.append(kwargs)

    class Handle:
        auth_url = "https://auth.openai.com/authorize?state=challenge"

        def wait(self):
            return types.SimpleNamespace(success=True)

    class Client:
        def __init__(self, config):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def login_chatgpt(self):
            return Handle()

    monkeypatch.setitem(sys.modules, "openai_codex", types.SimpleNamespace(Codex=Client, CodexConfig=Config))
    monkeypatch.setattr(sys, "argv", ["bridge", "browser"])
    monkeypatch.setattr(codex_auth_bridge, "emit", emitted.append)
    assert codex_auth_bridge.main() == 0
    assert "codex_bin" not in configurations[0]
    assert emitted[0]["state"] == "LOGIN_PENDING"
    assert emitted[-1]["state"] == "VERIFYING"


def test_expired_session_is_not_reported_ready(monkeypatch):
    value = manager(monkeypatch)
    value._state = {"state": "READY"}
    assert value.status()["state"] == "AUTH_REQUIRED"
