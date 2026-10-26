"""Documented public endpoints and sanitized, bounded HTTP operations."""

import json
import time
from email.utils import parsedate_to_datetime

import httpx

from .security import ConfigurationRequired, TransientFailure

ISSUER = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
AUTHORIZE = ISSUER + "/api/accounts/authorize"
TOKEN = ISSUER + "/api/accounts/oauth/token"
DISCOVERY = ISSUER + "/.well-known/openid-configuration"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
REQUIRED_SCOPES = {"chatgpt.tokens.use.direct", "resource.invoke", "offline_access"}
MAX_BODY = 2_000_000


class ChatGPTError(ConfigurationRequired):
    def __init__(self, message, state="WAITING_FOR_AUTH", code="authentication_required"):
        super().__init__(message)
        self.state, self.code = state, code


class ChatGPTTransient(TransientFailure):
    def __init__(self, retry_after=0):
        super().__init__("ChatGPT server or network temporarily unavailable. Retry later.")
        self.retry_after = retry_after


def retry_after(headers):
    value = headers.get("retry-after", "0")
    try:
        return max(0, min(86400, float(value)))
    except ValueError:
        try:
            return max(0, min(86400, parsedate_to_datetime(value).timestamp() - time.time()))
        except (ValueError, TypeError, OverflowError):
            return 0


def error_for(status, body=None, headers=None):
    error = body.get("error", {}) if isinstance(body, dict) else {}
    code = error.get("code", "") if isinstance(error, dict) else error if isinstance(error, str) else ""
    if status == 429 or code in {
        "subscription_sharing_usage_limit_exceeded",
        "subscription_sharing_usage_unavailable",
        "insufficient_quota",
    }:
        return ChatGPTError(
            "ChatGPT plan usage is unavailable or its limit was reached. Check usage and resume later.",
            "WAITING_FOR_LIMIT",
            "usage_limit",
        )
    if status == 401 or code in {"invalid_grant", "invalid_client", "token_expired", "invalid_token"}:
        return ChatGPTError("ChatGPT authentication expired or was revoked. Reconnect the same account.")
    if status == 403:
        return ChatGPTError(
            "ChatGPT plan permission was not granted for this request.",
            "WAITING_FOR_PLATFORM_APPROVAL",
            "permission_required",
        )
    if status == 404 or code in {"model_not_found", "model_not_available"}:
        return ChatGPTError(
            "Selected ChatGPT model is unavailable. Refresh the catalog and choose explicitly.",
            "WAITING_FOR_MODEL",
            "model_unavailable",
        )
    if status >= 500 or status in {408, 409}:
        return ChatGPTTransient(retry_after(headers or {}))
    return ChatGPTError(
        "ChatGPT rejected the request. Reconnect or check the selected model.",
        "WAITING_FOR_PLATFORM_APPROVAL",
        "request_rejected",
    )


def bounded_json(client, method, url, **kwargs):
    try:
        with client.stream(method, url, **kwargs) as response:
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_BODY:
                    raise ChatGPTError(
                        "ChatGPT response exceeded the allowed size.", "FAILED", "invalid_response"
                    )
                chunks.append(chunk)
            raw = b"".join(chunks)
            try:
                body = json.loads(raw) if raw else {}
            except (ValueError, UnicodeError):
                if not response.is_success:
                    raise error_for(response.status_code, headers=response.headers) from None
                raise ChatGPTError(
                    "ChatGPT returned an invalid response.", "FAILED", "invalid_response"
                ) from None
            if not response.is_success:
                raise error_for(response.status_code, body, response.headers)
            if not isinstance(body, dict):
                raise ChatGPTError("ChatGPT returned an invalid response.", "FAILED", "invalid_response")
            return body
    except httpx.HTTPError:
        raise ChatGPTTransient() from None
