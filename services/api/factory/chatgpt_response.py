"""Classify Responses transport failures without exposing bodies or credentials."""

import json
import re

from .chatgpt_http import MAX_BODY, ChatGPTError, error_for

KNOWN_CODES = {
    "subscription_sharing_usage_limit_exceeded",
    "subscription_sharing_usage_unavailable",
    "insufficient_quota",
    "invalid_grant",
    "invalid_client",
    "token_expired",
    "invalid_token",
    "invalid_api_key",
    "model_not_found",
    "model_not_available",
    "permission_denied",
    "insufficient_scope",
    "unsupported_parameter",
    "unsupported_value",
    "invalid_request_error",
    "invalid_request",
    "missing_required_parameter",
    "server_error",
    "rate_limit_exceeded",
    "streaming_not_supported",
}
KNOWN_PARAMETERS = {
    "stream",
    "store",
    "input",
    "instructions",
    "model",
    "tools",
    "temperature",
    "max_output_tokens",
}


def media_type(response):
    return response.headers.get("content-type", "").split(";", 1)[0].strip().lower()


def diagnostic(response, kind, code=None, message=None):
    media = media_type(response)
    # Header values are untrusted too. Never copy arbitrary values to logs.
    if media not in {
        "text/event-stream",
        "application/json",
        "application/problem+json",
        "text/html",
        "text/plain",
        "application/octet-stream",
        "",
    }:
        media = "other"
    request_id = response.headers.get("x-request-id", "")
    if not re.fullmatch(r"(?:req_[A-Za-z0-9_-]{1,120}|[a-fA-F0-9-]{16,64})", request_id):
        request_id = None
    return {
        "http_status": response.status_code,
        "content_type": media or "missing",
        "request_id": request_id,
        "format": kind,
        "error_code": code,
        "message": message,
    }


def attach(failure, details):
    failure.diagnostic = details
    if not hasattr(failure, "code"):
        failure.code = details["error_code"] or "response_protocol"
    failure.args = (
        str(failure)
        + " [HTTP "
        + str(details["http_status"])
        + "; Content-Type "
        + details["content_type"]
        + "; format "
        + details["format"]
        + "; request "
        + (details["request_id"] or "unavailable")
        + "]",
    )
    return failure


def safe_error_details(body):
    error = body.get("error") if isinstance(body, dict) else None
    code = error.get("code") or error.get("type") if isinstance(error, dict) else error
    code = code if isinstance(code, str) and code in KNOWN_CODES else "unrecognized_error"
    param = error.get("param") if isinstance(error, dict) else None
    if code in {
        "unsupported_parameter",
        "unsupported_value",
        "missing_required_parameter",
        "invalid_request_error",
        "invalid_request",
    }:
        message = "The service rejected the request format"
        if isinstance(param, str) and param in KNOWN_PARAMETERS:
            message += ": parameter " + param
        message += ". Update the request contract; reconnecting alone may not resolve it."
    else:
        message = "The service returned an error; private server message omitted."
    return code, message


async def sniff_missing_content_type(response):
    """Peek bounded bytes, then replay them. Missing headers never imply success."""
    iterator = response.aiter_bytes().__aiter__()
    held, prefix, matched = [], bytearray(), False
    markers = (b"data:", b"event:", b":", b"id:", b"retry:")
    async for chunk in iterator:
        held.append(chunk)
        prefix.extend(chunk)
        if len(prefix) > MAX_BODY:
            raise attach(
                ChatGPTError("ChatGPT response exceeded the allowed size.", "FAILED", "response_too_large"),
                diagnostic(response, "oversized", "response_too_large"),
            )
        start = bytes(prefix)
        if len(start) < 3 and b"\xef\xbb\xbf".startswith(start):
            continue
        start = start.removeprefix(b"\xef\xbb\xbf").lstrip(b"\r\n")
        if any(start.startswith(marker) for marker in markers):
            matched = True
            break
        if len(prefix) >= 1024 or (start and not any(marker.startswith(start) for marker in markers)):
            break

    async def replay():
        for chunk in held:
            yield chunk
        async for chunk in iterator:
            yield chunk

    return matched, replay()


async def non_sse_failure(response, chunks=None):
    raw = bytearray()
    async for chunk in chunks if chunks is not None else response.aiter_bytes():
        raw.extend(chunk)
        if len(raw) > MAX_BODY:
            return attach(
                ChatGPTError("ChatGPT response exceeded the allowed size.", "FAILED", "response_too_large"),
                diagnostic(response, "oversized", "response_too_large"),
            )
    if not raw.strip():
        kind, body = "empty", None
    else:
        try:
            body = json.loads(raw)
            kind = "json"
        except (ValueError, UnicodeError):
            body = None
            prefix = bytes(raw[:256]).lstrip().lower()
            kind = (
                "html"
                if media_type(response) == "text/html" or prefix.startswith((b"<!doctype html", b"<html"))
                else "sse_wrong_content_type"
                if prefix.startswith((b"data:", b"event:", b":"))
                else "unknown"
            )
    if isinstance(body, dict) and body.get("error"):
        code, message = safe_error_details(body)
        failure = error_for(response.status_code if not response.is_success else 400, body, response.headers)
        if code in {
            "unsupported_parameter",
            "unsupported_value",
            "missing_required_parameter",
            "invalid_request_error",
            "invalid_request",
        }:
            failure = ChatGPTError(message, "FAILED", "request_contract")
        return attach(failure, diagnostic(response, "json_error", code, message))
    if isinstance(body, dict) and body.get("object") == "response" and body.get("status") == "completed":
        kind = "json_completed"
    if not response.is_success:
        failure = error_for(response.status_code, headers=response.headers)
    else:
        messages = {
            "json_completed": "ChatGPT returned JSON marked completed instead of the required SSE stream. No result was accepted; check the request ID with service support.",
            "json": "ChatGPT returned unexpected JSON instead of SSE. No result was accepted; check the request ID with service support.",
            "html": "ChatGPT returned HTML instead of SSE. Check network filtering, a gateway or service availability; no page content was saved.",
            "empty": "ChatGPT returned an empty response instead of SSE. Retry later and keep the request ID for support.",
            "sse_wrong_content_type": "ChatGPT returned SSE-like data with an incompatible Content-Type. Check the network gateway or service response headers; no output was accepted.",
            "unknown": "ChatGPT returned an unsupported response format instead of SSE. No content was saved; check the request ID with support.",
        }
        failure = ChatGPTError(messages[kind], "FAILED", "response_contract")
    code = getattr(failure, "code", "transient") if not response.is_success else "response_contract"
    return attach(failure, diagnostic(response, kind, code, str(failure)))
