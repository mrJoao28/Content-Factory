"""Manage one bounded login subprocess, independently of render/inference jobs."""

import json
import os
import subprocess
import sys
import threading
import time

from .config import ROOT
from .security import terminate_tree


class LoginManager:
    timeout = 300
    startup_timeout = 30

    def __init__(self):
        self._lock = threading.RLock()
        self._process = None
        self._state = None
        self._started = 0.0
        self._checked = 0.0
        self._generation = 0

    def _verify(self):
        from .codex import cli_auth_status

        return cli_auth_status()

    def status(self):
        with self._lock:
            pending = self._state and self._state["state"] in {"STARTING", "LOGIN_PENDING", "VERIFYING"}
            if pending:
                now = time.monotonic()
                limit = self.startup_timeout if self._state["state"] == "STARTING" else self.timeout
                if now - self._started > limit:
                    self._stop()
                    self._state = {
                        "state": "TIMED_OUT",
                        "instructions": "Login timed out. Close an old terminal login with Ctrl+C and retry, or choose device code login.",
                    }
                elif now - self._checked > 3:
                    self._checked = now
                    verified = self._verify()
                    if verified["state"] == "READY":
                        self._stop()
                        self._state = verified
                return dict(self._state)
            verified = self._verify()
            if verified["state"] == "READY" or self._state is None or self._state["state"] == "READY":
                return verified
            return dict(self._state)

    def start(self, mode="browser"):
        if mode not in {"browser", "device"}:
            raise ValueError("Login mode must be browser or device")
        with self._lock:
            current = self.status()
            if current["state"] in {"READY", "STARTING", "LOGIN_PENDING", "VERIFYING"}:
                return current
            self._stop()
            env = os.environ.copy()
            for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "GOOGLE_CLIENT_SECRET", "TIKTOK_CLIENT_SECRET"):
                env.pop(name, None)
            env["PYTHONPATH"] = str(ROOT / "services/api")
            self._state = {"state": "STARTING", "instructions": "Starting the official Codex login..."}
            self._started = time.monotonic()
            self._checked = self._started
            try:
                self._process = subprocess.Popen(
                    [sys.executable, "-m", "factory.codex_auth_bridge", mode],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    env=env,
                    cwd=ROOT,
                    shell=False,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    start_new_session=os.name != "nt",
                )
            except OSError:
                self._state = {
                    "state": "UNAVAILABLE",
                    "instructions": "Could not start the official login process. Run codex login in PowerShell.",
                }
                return dict(self._state)
            generation = self._generation
            threading.Thread(target=self._read, args=(self._process, generation), daemon=True).start()
            threading.Thread(target=self._watch, args=(generation,), daemon=True).start()
            return dict(self._state)

    def _watch(self, generation):
        while True:
            time.sleep(1)
            with self._lock:
                if (
                    generation != self._generation
                    or not self._state
                    or self._state["state"] not in {"STARTING", "LOGIN_PENDING", "VERIFYING"}
                ):
                    return
            self.status()

    def _read(self, process, generation):
        try:
            for line in process.stdout:
                message = json.loads(line)
                if message.get("state") not in {"LOGIN_PENDING", "VERIFYING", "FAILED", "UNAVAILABLE"}:
                    continue
                with self._lock:
                    if generation != self._generation:
                        return
                    self._state = {
                        key: message[key]
                        for key in ("state", "instructions", "url", "user_code")
                        if key in message
                    }
            process.wait(timeout=5)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        finally:
            process.stdout.close()
            with self._lock:
                if generation == self._generation:
                    if self._state["state"] in {"STARTING", "LOGIN_PENDING", "VERIFYING"}:
                        verified = self._verify()
                        self._state = (
                            verified
                            if verified["state"] == "READY"
                            else {
                                "state": "FAILED",
                                "instructions": "Login ended without a confirmed ChatGPT session. Retry with device code or run codex login status in PowerShell.",
                            }
                        )
                    self._stop()

    def _stop(self):
        self._generation += 1
        if self._process is not None:
            terminate_tree(self._process)
            self._process = None

    def cancel(self):
        with self._lock:
            self._stop()
            self._state = {
                "state": "CANCELLED",
                "instructions": "Login cancelled. Existing saved sessions were not revoked.",
            }
            return dict(self._state)


login_manager = LoginManager()
