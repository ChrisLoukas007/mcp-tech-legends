"""Who is calling, and on whose behalf.

This API is called by a SERVICE (hall-of-fame-mcp) acting for a USER. It checks both:
    1. the bearer token: signed by Keycloak, aud=hall-of-fame-api, azp is a trusted caller
    2. the X-Acting-User header: which user the service acts for, trusted ONLY because (1) passed

The MCP server never forwards the user's own token here (no token passthrough). The standard,
stronger next step is OAuth token exchange (RFC 8693), which puts the user inside the token.

The private app is "someone else's system", so it verifies tokens itself instead of importing
the MCP kit.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

USERNAME = re.compile(r"^[a-z0-9_-]{2,40}$")


@dataclass(frozen=True)
class Caller:
    service: str
    user: str


class CallerVerifier:
    def __init__(self, *, issuer: str, audience: str, trusted_callers: tuple[str, ...],
                 key_resolver: Callable[[str], Any]) -> None:  # fmt: skip
        self._issuer = issuer
        self._audience = audience
        self._trusted = trusted_callers
        self._key_resolver = key_resolver

    def verify(self, authorization: str | None, x_acting_user: str | None) -> Caller:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
        token = authorization.removeprefix("Bearer ")
        try:
            claims = jwt.decode(token, self._key_resolver(token), algorithms=["RS256", "ES256"],
                                audience=self._audience, issuer=self._issuer, leeway=30)  # fmt: skip
        except (jwt.PyJWTError, jwt.PyJWKClientError) as exc:
            logger.info("token rejected: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from None
        service = str(claims.get("azp", ""))
        if service not in self._trusted:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "caller not allowed")
        if not x_acting_user or not USERNAME.match(x_acting_user):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Acting-User header missing or invalid")
        return Caller(service=service, user=x_acting_user)


def jwks_resolver(jwks_url: str) -> Callable[[str], Any]:
    client = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=300, timeout=5)
    return lambda token: client.get_signing_key_from_jwt(token).key
