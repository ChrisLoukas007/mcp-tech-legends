"""The verifier must accept only tokens signed by the IdP, for THIS server's audience, unexpired."""

from __future__ import annotations

import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from mcp_kit.auth import JwtTokenVerifier

ISSUER = "http://idp.test/realms/legends"
AUDIENCE = "wiki-mcp"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _claims(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    base = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "f1b2",
        "preferred_username": "ada",
        "azp": "agent-cli",
        "iat": now,
        "exp": now + 300,
        "scope": "wiki:read",
        "realm_access": {"roles": ["legends-curator"]},
    }
    return {**base, **overrides}


def _sign(claims: dict[str, Any], key: Any = _KEY) -> str:
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture
def verifier() -> JwtTokenVerifier:
    return JwtTokenVerifier(issuer=ISSUER, audience=AUDIENCE, key_resolver=lambda _token: _KEY.public_key())


async def test_verify_token_when_valid_then_returns_user_scopes_and_roles(verifier: JwtTokenVerifier) -> None:
    token = await verifier.verify_token(_sign(_claims()))
    assert token is not None
    assert token.subject == "ada"
    assert token.client_id == "agent-cli"
    assert token.scopes == ["wiki:read"]
    assert token.claims is not None and token.claims["roles"] == ["legends-curator"]


@pytest.mark.parametrize(
    ("description", "claims"),
    [
        ("token minted for another MCP server", _claims(aud="figures-db-mcp")),
        ("wrong issuer", _claims(iss="http://evil.test/realms/legends")),
        ("expired", _claims(exp=int(time.time()) - 3600, iat=int(time.time()) - 7200)),
        ("missing subject", {k: v for k, v in _claims().items() if k != "sub"}),
    ],
)
async def test_verify_token_when_claims_invalid_then_rejected(
    verifier: JwtTokenVerifier, description: str, claims: dict[str, Any]
) -> None:
    assert await verifier.verify_token(_sign(claims)) is None, description


async def test_verify_token_when_signed_by_unknown_key_then_rejected(verifier: JwtTokenVerifier) -> None:
    assert await verifier.verify_token(_sign(_claims(), key=_OTHER_KEY)) is None


async def test_verify_token_when_hs256_forgery_then_rejected(verifier: JwtTokenVerifier) -> None:
    forged = jwt.encode(_claims(), "not-the-idp-key-but-long-enough-for-hmac", algorithm="HS256")
    assert await verifier.verify_token(forged) is None
