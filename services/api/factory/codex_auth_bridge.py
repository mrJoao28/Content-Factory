"""Isolated official SDK login. Emits only login challenges and completion, never tokens."""

import json
import sys
from urllib.parse import urlparse


def emit(value):
    print(json.dumps(value), flush=True)


def official_url(value):
    parsed = urlparse(value)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not (
        host == "chatgpt.com"
        or host.endswith(".chatgpt.com")
        or host == "openai.com"
        or host.endswith(".openai.com")
    ):
        raise ValueError("Unexpected login URL")
    return value


def main():
    try:
        from openai_codex import Codex, CodexConfig

        # Use the matching runtime shipped by the official SDK, not an unrelated global CLI.
        config = CodexConfig(
            client_name="ai_content_factory_login",
            client_title="AI Content Factory",
        )
        with Codex(config) as client:
            if sys.argv[1] == "device":
                handle = client.login_chatgpt_device_code()
                emit(
                    {
                        "state": "LOGIN_PENDING",
                        "url": official_url(handle.verification_url),
                        "user_code": handle.user_code,
                        "instructions": "Open the link and enter the code. Enable device login in ChatGPT security settings if required.",
                    }
                )
            else:
                handle = client.login_chatgpt()
                emit(
                    {
                        "state": "LOGIN_PENDING",
                        "url": official_url(handle.auth_url),
                        "instructions": "Open the official sign-in link and finish in the browser.",
                    }
                )
            result = handle.wait()
            emit(
                {
                    "state": "VERIFYING" if result.success else "FAILED",
                    "instructions": "Checking the saved CLI session."
                    if result.success
                    else "Official login failed. Retry or use device code login.",
                }
            )
    except ImportError:
        emit(
            {
                "state": "UNAVAILABLE",
                "instructions": "Install the official Python SDK: .venv\\Scripts\\python.exe -m pip install openai-codex. Or run codex login in PowerShell.",
            }
        )
        return 1
    except Exception:
        # SDK exceptions may contain account details or HTTP payloads. Do not expose them.
        emit(
            {
                "state": "FAILED",
                "instructions": "Official login could not start or complete. Close an older pending login (Ctrl+C), verify network access, or try device code login.",
            }
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
