"""Bearer-token verification: every HTTP server is an OAuth 2.1 resource server.

The identity provider (Keycloak) signs JWTs. This module checks the signature against the
provider's public keys (JWKS) and validates issuer, audience and expiry. The SDK calls
`verify_token` on every HTTP request; returning None makes it answer 401 before any tool runs.

Each server has its own audience, so a token minted for figures-db-mcp is useless at wiki-mcp.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import anyio.to_thread
import jwt
from mcp.server.auth.provider import AccessToken

logger = logging.getLogger(__name__)

SigningKeyResolver = Callable[[str], Any]

ALLOWED_ALGORITHMS = ["RS256", "ES256"]  # pinned: blocks HS256 algorithm-confusion forgeries


def jwks_resolver(jwks_url: str) -> SigningKeyResolver:
    """Fetch and cache the IdP's public keys; refreshed when an unknown key id appears."""
    client = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=300, timeout=5)

    def resolve(token: str) -> Any:
        return client.get_signing_key_from_jwt(token).key

    return resolve


class JwtTokenVerifier:
    """Implements the SDK's `TokenVerifier` protocol for JWT access tokens."""

    def __init__(self, *, issuer: str, audience: str, key_resolver: SigningKeyResolver) -> None:
        self._issuer = issuer
        self._audience = audience
        self._key_resolver = key_resolver

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            # Key lookup may hit the network (JWKS refresh), so keep it off the event loop.
            key = await anyio.to_thread.run_sync(self._key_resolver, token)
            claims = jwt.decode(
                token,
                key,
                algorithms=ALLOWED_ALGORITHMS,
                audience=self._audience,
                issuer=self._issuer,
                leeway=30,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except (jwt.PyJWTError, jwt.PyJWKClientError) as exc:
            # Log the failure class only: the token itself is a credential.
            logger.info("bearer token rejected: %s", type(exc).__name__)
            return None
        return access_token_from_claims(token, claims, self._audience)


def access_token_from_claims(token: str, claims: dict[str, Any], audience: str) -> AccessToken:
    scope_claim = claims.get("scope", "")
    realm_access = claims.get("realm_access") or {}
    return AccessToken(
        token=token,
        client_id=str(claims.get("azp") or claims.get("client_id") or "unknown"),
        scopes=scope_claim.split() if isinstance(scope_claim, str) else [],
        expires_at=int(claims["exp"]),
        resource=audience,
        subject=str(claims.get("preferred_username") or claims["sub"]),
        claims={"iss": claims["iss"], "roles": list(realm_access.get("roles", []))},
    )
