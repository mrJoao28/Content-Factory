"""OIDC validation through PyJWT; public-client OAuth has no client secret."""

import base64
import hashlib
import secrets
import time
from urllib.parse import urlparse

import jwt
from pydantic import BaseModel, Field, SecretStr, ValidationError

from .chatgpt_http import DISCOVERY, ISSUER, REQUIRED_SCOPES, TOKEN, ChatGPTError, bounded_json


class TokenSet(BaseModel):
    access_token: SecretStr = Field(min_length=1, max_length=32768)
    refresh_token: SecretStr = Field(min_length=1, max_length=32768)
    id_token: SecretStr | None = Field(default=None, max_length=32768)
    token_type: str
    expires_in: int = Field(gt=0, le=86400)
    scope: str | None = Field(default=None, max_length=4000)


def auth_endpoint(value):
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "auth.openai.com"
        or parsed.port not in {None, 443}
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ChatGPTError("Invalid OpenAI discovery endpoint.", "FAILED", "invalid_discovery")
    return value


class IdentityValidator:
    def __init__(self, client):
        self.client = client
        self._metadata = None
        self._keys = None
        self._keys_at = 0

    def metadata(self):
        if self._metadata is None:
            value = bounded_json(self.client, "GET", DISCOVERY)
            if value.get("issuer") != ISSUER or value.get("token_endpoint") != TOKEN:
                raise ChatGPTError("Invalid OpenAI discovery document.", "FAILED", "invalid_discovery")
            auth_endpoint(value.get("jwks_uri", ""))
            auth_endpoint(value.get("revocation_endpoint", ""))
            self._metadata = value
        return self._metadata

    def verify(self, raw, client_id, nonce=None, access_token=None):
        try:
            metadata = self.metadata()
            header = jwt.get_unverified_header(raw)
            allowed = set(metadata.get("id_token_signing_alg_values_supported", ["RS256"])) & {
                "RS256",
                "ES256",
            }
            algorithm = header.get("alg")
            if algorithm not in allowed or not isinstance(header.get("kid"), str):
                raise ValueError("algorithm")
            key = None
            for attempt in range(2):
                if self._keys is None or time.monotonic() - self._keys_at > 3600 or attempt:
                    self._keys = bounded_json(self.client, "GET", metadata["jwks_uri"])
                    self._keys_at = time.monotonic()
                matches = [
                    k
                    for k in self._keys.get("keys", [])
                    if k.get("kid") == header["kid"]
                    and k.get("use", "sig") == "sig"
                    and k.get("alg", algorithm) == algorithm
                    and "verify" in k.get("key_ops", ["verify"])
                ]
                if len(matches) == 1:
                    key = jwt.PyJWK.from_dict(matches[0], algorithm=algorithm).key
                    break
            if key is None:
                raise ValueError("key")
            payload = jwt.decode(
                raw,
                key,
                algorithms=[algorithm],
                issuer=ISSUER,
                audience=client_id,
                leeway=5,
                options={"require": ["sub", "iss", "aud", "iat", "exp"]},
            )
            if not isinstance(payload["sub"], str) or not 1 <= len(payload["sub"]) <= 500:
                raise ValueError("subject")
            if nonce is not None and (
                not isinstance(payload.get("nonce"), str)
                or not secrets.compare_digest(payload["nonce"], nonce)
            ):
                raise ValueError("nonce")
            audience = payload["aud"]
            if (isinstance(audience, list) and len(audience) > 1 or "azp" in payload) and payload.get(
                "azp"
            ) != client_id:
                raise ValueError("azp")
            if "at_hash" in payload and access_token is not None:
                digest = jwt.get_algorithm_by_name(algorithm).compute_hash_digest(access_token.encode())
                expected = base64.urlsafe_b64encode(digest[: len(digest) // 2]).rstrip(b"=").decode()
                if not secrets.compare_digest(expected, payload["at_hash"]):
                    raise ValueError("at_hash")
            return payload
        except (jwt.PyJWTError, ValueError, TypeError, KeyError, AttributeError):
            raise ChatGPTError(
                "ChatGPT identity validation failed. Start a fresh authorization.",
                "FAILED",
                "invalid_identity",
            ) from None

    def tokens(self, value, client_id, nonce=None, previous=None):
        try:
            parsed = TokenSet.model_validate(value)
            if parsed.token_type.lower() != "bearer":
                raise ValueError("token_type")
            scopes = (
                parsed.scope.split()
                if parsed.scope is not None
                else previous.get("scopes", [])
                if previous
                else []
            )
            if not REQUIRED_SCOPES.issubset(scopes):
                raise ChatGPTError(
                    "ChatGPT plan permission was not granted. Reauthorize and allow plan usage.",
                    "WAITING_FOR_PLATFORM_APPROVAL",
                    "permission_required",
                )
            if previous is None and parsed.id_token is None:
                raise ValueError("identity missing")
            identity = (
                self.verify(
                    parsed.id_token.get_secret_value(),
                    client_id,
                    nonce,
                    parsed.access_token.get_secret_value(),
                )
                if parsed.id_token
                else None
            )
            if previous and identity and identity["sub"] != previous["subject"]:
                raise ValueError("identity changed")
            return {
                "access": parsed.access_token.get_secret_value(),
                "refresh": parsed.refresh_token.get_secret_value(),
                "id_token": parsed.id_token.get_secret_value() if parsed.id_token else previous["id_token"],
                "subject": identity["sub"] if identity else previous["subject"],
                "email": str(identity.get("email", ""))[:200] if identity else previous.get("email", ""),
                "expires_at": time.time() + parsed.expires_in,
                "scopes": sorted(set(scopes)),
            }
        except (ValidationError, ValueError, KeyError, TypeError):
            raise ChatGPTError(
                "ChatGPT returned incomplete or mismatched credentials. Reconnect.",
                "FAILED",
                "invalid_tokens",
            ) from None


def challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
