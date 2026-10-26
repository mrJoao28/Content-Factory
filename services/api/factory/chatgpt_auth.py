"""Temporary loopback listener for Content Factory's own public-client OAuth."""

import re
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

from .chatgpt_accounts import ChatGPTAccounts, account_in
from .chatgpt_http import AUTHORIZE, RESOURCE, SCOPES, TOKEN, ChatGPTError, bounded_json
from .chatgpt_identity import challenge
from .config import settings


class ChatGPTLogin:
    def __init__(self, accounts=None):
        self.accounts = accounts or ChatGPTAccounts()
        self._lock = threading.RLock()
        self._attempt = None

    def status(self):
        with self._lock:
            if not self._attempt:
                return {"state": "IDLE"}
            return {k: self._attempt[k] for k in ("id", "state", "url", "message") if k in self._attempt}

    def start(self, account_id=None, open_browser=True):
        with self._lock:
            if self._attempt and self._attempt["state"] in {"WAITING", "EXCHANGING"}:
                return self.status()
            state = self.accounts.store.update(lambda current: current)
            selected = account_in(state, account_id) if account_id else None
            if account_id and not selected:
                raise ValueError("Unknown ChatGPT connection")
            pending = {
                "id": str(uuid4()),
                "state": "WAITING",
                "state_token": secrets.token_urlsafe(32),
                "nonce": secrets.token_urlsafe(32),
                "verifier": secrets.token_urlsafe(64),
                "selected": selected,
                "consumed": False,
                "deadline": time.monotonic() + settings.chatgpt_login_timeout_seconds,
            }
            manager = self

            class Handler(BaseHTTPRequestHandler):
                def setup(self):
                    super().setup()
                    self.connection.settimeout(3)

                def log_message(self, *args):
                    pass  # Authorization codes, state and URLs never go to logs.

                def do_GET(self):
                    status, message = manager.callback(
                        pending, self.path, self.headers.get("Host", ""), self.headers.get("Origin")
                    )
                    body = (
                        "<!doctype html><meta charset=utf-8><title>Content Factory</title><h1>Content Factory</h1><p>"
                        + message
                        + "</p><p>Return to the Content Factory Settings tab.</p>"
                    ).encode()
                    self.send_response(status)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Referrer-Policy", "no-referrer")
                    self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
                    self.end_headers()
                    try:
                        self.wfile.write(body)
                    except OSError:
                        pass

                def do_POST(self):
                    self.send_error(405)

                do_PUT = do_POST
                do_DELETE = do_POST
                do_HEAD = do_POST
                do_OPTIONS = do_POST

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            server.daemon_threads = True
            server.block_on_close = False
            pending["server"] = server
            pending["redirect"] = f"http://127.0.0.1:{server.server_port}/auth/callback"
            client_id = (
                selected["client_id"]
                if selected
                else state.get("pending_client_id") or "dynamic_agent_client"
            )
            pending["client_id"] = client_id
            params = {
                "client_id": client_id,
                "ext_agent_host_id": state["host_id"],
                "response_type": "code",
                "redirect_uri": pending["redirect"],
                "scope": SCOPES,
                "resource": RESOURCE,
                "state": pending["state_token"],
                "nonce": pending["nonce"],
                "code_challenge_method": "S256",
                "code_challenge": challenge(pending["verifier"]),
            }
            if client_id == "dynamic_agent_client":
                params["agent_name_hint"] = "Content Factory"
            elif selected and selected.get("email"):
                params["login_hint"] = selected["email"]
            # Do not include retained ID tokens in a URL returned to browser JavaScript.
            pending["url"] = AUTHORIZE + "?" + urlencode(params)
            self._attempt = pending
            threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True).start()
            timer = threading.Timer(
                settings.chatgpt_login_timeout_seconds,
                lambda: self._finish(pending, "TIMED_OUT", "Authorization timed out. Start again."),
            )
            timer.daemon = True
            pending["timer"] = timer
            timer.start()
            if open_browser:
                threading.Thread(target=self._open, args=(pending["url"],), daemon=True).start()
            return self.status()

    @staticmethod
    def _open(url):
        try:
            webbrowser.open(url, new=2)
        except Exception:
            pass

    def _finish(self, pending, state, message):
        with self._lock:
            if self._attempt is not pending or pending["state"] not in {"WAITING", "EXCHANGING"}:
                return
            pending.update(state=state, message=message)
            for field in ("url", "state_token", "nonce", "verifier", "selected"):
                pending.pop(field, None)
            pending["timer"].cancel()
            pending["server"].shutdown()
            pending["server"].server_close()

    def cancel(self):
        with self._lock:
            if self._attempt:
                self._finish(
                    self._attempt,
                    "CANCELLED",
                    "Authorization cancelled. Existing connections were preserved.",
                )
            return self.status()

    def callback(self, pending, path, host, origin=None):
        with self._lock:
            if (
                self._attempt is not pending
                or pending["state"] != "WAITING"
                or pending["consumed"]
                or time.monotonic() >= pending["deadline"]
            ):
                return 409, "This authorization attempt is no longer valid."
            if origin not in {None, "https://auth.openai.com"}:
                return 400, "Invalid callback origin."
            uri = urlsplit(pending["redirect"])
            parsed = urlsplit(path)
            if (
                host != uri.netloc
                or parsed.path != uri.path
                or parsed.scheme
                or parsed.netloc
                or len(path) > 16000
                or re.search(r"%(?![0-9a-fA-F]{2})", path)
            ):
                return 400, "Invalid authorization callback."
            try:
                values = parse_qs(
                    parsed.query, keep_blank_values=True, max_num_fields=10, strict_parsing=True
                )
                allowed = {"code", "state", "client_id", "scope", "error", "error_description", "error_uri"}
                if set(values) - allowed or any(len(v) != 1 or len(v[0]) > 8000 for v in values.values()):
                    raise ValueError("parameters")
                received = values.get("state", [""])[0]
                if not secrets.compare_digest(received, pending["state_token"]):
                    raise ValueError("state")
            except (ValueError, TypeError):
                return 400, "Authorization state or parameters did not match."
            pending["consumed"] = True
            if "error" in values:
                self._finish(
                    pending, "DENIED", "Authorization was denied. Existing connections were preserved."
                )
                return 400, "Authorization was denied."
            supplied = values.get("client_id", [None])[0]
            issued = supplied or pending["client_id"]
            if (
                not re.fullmatch(r"[a-zA-Z0-9_-]{1,200}", issued or "")
                or issued == "dynamic_agent_client"
                or (pending["client_id"] != "dynamic_agent_client" and issued != pending["client_id"])
                or not values.get("code", [""])[0]
            ):
                self._finish(
                    pending, "ERROR", "Registration was incomplete or did not match the selected connection."
                )
                return 400, "Registration did not match."
            pending["state"] = "EXCHANGING"
            nonce, verifier, redirect = pending["nonce"], pending["verifier"], pending["redirect"]
            selected = pending["selected"]
        try:
            # An issued registration survives an invalid_grant without becoming an active connection.
            if selected is None:
                self.accounts.store.update(lambda state: state.update(pending_client_id=issued))
            value = bounded_json(
                self.accounts.client,
                "POST",
                TOKEN,
                data={
                    "grant_type": "authorization_code",
                    "client_id": issued,
                    "code": values["code"][0],
                    "code_verifier": verifier,
                    "redirect_uri": redirect,
                    "resource": RESOURCE,
                },
            )
            tokens = self.accounts.identity.tokens(value, issued, nonce)
            if selected and tokens["subject"] != selected["subject"]:
                raise ChatGPTError(
                    "Authorized identity does not match the selected account.", "FAILED", "identity_mismatch"
                )
            with self._lock:
                if self._attempt is not pending or pending["state"] != "EXCHANGING":
                    return 409, "Authorization was cancelled or expired."

                def save(state):
                    account = next(
                        (
                            a
                            for a in state["accounts"]
                            if a["client_id"] == issued and a["subject"] == tokens["subject"]
                        ),
                        None,
                    )
                    if account is None:
                        if any(a["client_id"] == issued for a in state["accounts"]):
                            raise ChatGPTError(
                                "ChatGPT identity does not match this saved registration.",
                                "FAILED",
                                "identity_mismatch",
                            )
                        if len(state["accounts"]) >= 50:
                            raise ValueError("Connection limit reached")
                        account = {"id": str(uuid4()), "client_id": issued, "subject": tokens["subject"]}
                        state["accounts"].append(account)
                    for item in state["accounts"]:
                        item["generation"] = secrets.token_hex(16)
                    email = re.sub(r"[\x00-\x1f\x7f]", "", tokens["email"])
                    account.update(
                        tokens=tokens,
                        email=email,
                        label=(email or "ChatGPT account") + " / " + account["id"][:8],
                        inference_verified=False,
                        auth_state=None,
                    )
                    state["active_id"] = account["id"]
                    state.pop("pending_client_id", None)

                self.accounts.store.update(save)
                self._finish(
                    pending,
                    "COMPLETE",
                    "ChatGPT connected. Refresh the catalog and choose a model. Inference is not tested yet.",
                )
            return 200, "Authorization completed."
        except ChatGPTError as error:
            self._finish(pending, "ERROR", str(error))
        except Exception:
            self._finish(
                pending,
                "ERROR",
                "Authorization could not complete. Check secure storage and connectivity, then retry.",
            )
        return 400, "Authorization could not complete. Return to Settings to retry."
