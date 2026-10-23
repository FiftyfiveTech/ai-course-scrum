"""
Inbound Bot Framework token check (POC-02).

Teams calls POST /api/messages with `Authorization: Bearer <JWT>`. A genuine token is
RS256-signed by the Bot Framework, has issuer `https://api.botframework.com`, and its
audience is this bot's Microsoft App id. We verify the signature against the Bot
Framework JWKS and check issuer + audience + expiry; anything else is rejected.

The signing-key lookup is injected (`key_resolver`) so tests can sign with a local
keypair and verify offline — no network, deterministic, zero-spend. Production resolves
keys from the published JWKS via `botframework_validator`.
"""

from __future__ import annotations

import logging
import urllib.request
import json
from typing import Any, Callable, Sequence

import jwt
from jwt import InvalidTokenError, PyJWKClient

logger = logging.getLogger(__name__)

BOTFRAMEWORK_ISSUER = "https://api.botframework.com"
BOTFRAMEWORK_OPENID_CONFIG = "https://login.botframework.com/v1/.well-known/openidconfiguration"

# key_resolver: given the raw token string, return the key to verify it with.
KeyResolver = Callable[[str], Any]


class TokenError(Exception):
    """Raised when an inbound token is missing, malformed, or fails verification."""


class TokenValidator:
    def __init__(
        self,
        audience: str,
        key_resolver: KeyResolver,
        issuers: Sequence[str] = (BOTFRAMEWORK_ISSUER,),
        leeway: int = 300,
    ) -> None:
        self.audience = audience
        self.key_resolver = key_resolver
        self.issuers = tuple(issuers)
        self.leeway = leeway

    def validate(self, auth_header: str | None) -> dict[str, Any]:
        """Verify a Bearer token. Returns its claims, or raises TokenError."""
        if not auth_header:
            raise TokenError("missing Authorization header")
        scheme, _, token = auth_header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise TokenError("Authorization header is not a Bearer token")
        token = token.strip()

        try:
            key = self.key_resolver(token)
        except Exception as exc:  # JWKS lookup / unknown kid
            raise TokenError(f"could not resolve signing key: {exc}") from exc

        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.audience,
                leeway=self.leeway,
                options={"require": ["exp", "iss", "aud"]},
            )
        except InvalidTokenError as exc:
            raise TokenError(f"token failed verification: {exc}") from exc

        if claims.get("iss") not in self.issuers:
            raise TokenError(f"untrusted issuer {claims.get('iss')!r}")
        return claims


def _jwks_uri(openid_config_url: str) -> str:
    with urllib.request.urlopen(openid_config_url, timeout=10) as resp:
        return json.load(resp)["jwks_uri"]


def botframework_validator(
    audience: str,
    openid_config_url: str = BOTFRAMEWORK_OPENID_CONFIG,
) -> TokenValidator:
    """Production validator: resolve signing keys from the Bot Framework JWKS."""
    jwk_client = PyJWKClient(_jwks_uri(openid_config_url))

    def resolve(token: str) -> Any:
        return jwk_client.get_signing_key_from_jwt(token).key

    return TokenValidator(audience=audience, key_resolver=resolve)
