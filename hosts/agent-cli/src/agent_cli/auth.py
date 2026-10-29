"""How the host gets a DIFFERENT token for each MCP server.

    1. log in once (browser + PKCE, or a password grant for automated tests), asking for the
       scopes of every server. That login token has all three audiences: it is never sent anywhere.
    2. for each server, use the refresh token to ask for ONLY that server's scopes. Keycloak
       returns a token whose `aud` is that server alone (infra/keycloak/realm.json maps scope -> aud).
    3. every HTTP request to a server gets its own token, refreshed when it nears expiry.

So a token stolen from wiki-mcp's logs is useless at hall-of-fame-mcp.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
import webbrowser
from collections.abc import AsyncGenerator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx2

REFRESH_MARGIN_SECONDS = 30


class TokenBroker:
    def __init__(self, issuer_url: str, client_id: str, server_scopes: dict[str, str],
                 client_secret: str | None = None) -> None:  # fmt: skip
        self._token_url = f"{issuer_url}/protocol/openid-connect/token"
        self._auth_url = f"{issuer_url}/protocol/openid-connect/auth"
        self._client_id = client_id
        self._client_secret = client_secret
        self._server_scopes = server_scopes
        self._refresh_token: str | None = None
        self._cache: dict[str, tuple[str, float]] = {}

    @property
    def all_scopes(self) -> str:
        return " ".join(sorted({s for scopes in self._server_scopes.values() for s in scopes.split()}))

    async def password_login(self, username: str, password: str) -> None:
        """Automated tests only (client agent-cli-test). Real users log in with `pkce_login`."""
        await self._grant({"grant_type": "password", "username": username, "password": password,
                           "scope": self.all_scopes})  # fmt: skip

    async def pkce_login(self, redirect_port: int) -> None:
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(16)
        redirect_uri = f"http://127.0.0.1:{redirect_port}/callback"
        query = urlencode(
            {
                "client_id": self._client_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "scope": self.all_scopes,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": state,
            }
        )
        code = _wait_for_code(f"{self._auth_url}?{query}", redirect_port, state)
        await self._grant({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
                           "code_verifier": verifier})  # fmt: skip

    async def token_for(self, server: str) -> str:
        cached = self._cache.get(server)
        if cached and time.monotonic() < cached[1] - REFRESH_MARGIN_SECONDS:
            return cached[0]
        if self._refresh_token is None:
            raise RuntimeError("not logged in")
        data = await self._grant({"grant_type": "refresh_token", "refresh_token": self._refresh_token,
                                  "scope": self._server_scopes[server]})  # fmt: skip
        self._cache[server] = (data["access_token"], time.monotonic() + int(data["expires_in"]))
        return str(data["access_token"])

    async def _grant(self, form: dict[str, str]) -> dict[str, Any]:
        form = {**form, "client_id": self._client_id}
        if self._client_secret:
            form["client_secret"] = self._client_secret
        async with httpx2.AsyncClient(timeout=10) as http:
            response = await http.post(self._token_url, data=form)
        if response.status_code != 200:
            raise RuntimeError(
                f"token request failed ({response.status_code}): {response.json().get('error')}"
            )
        data: dict[str, Any] = response.json()
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        return data


class ServerTokenAuth(httpx2.Auth):
    """Attach the right server's token to every request (fetched or refreshed as needed)."""

    def __init__(self, broker: TokenBroker, server: str) -> None:
        self._broker = broker
        self._server = server

    async def async_auth_flow(
        self, request: httpx2.Request
    ) -> AsyncGenerator[httpx2.Request, httpx2.Response]:
        request.headers["Authorization"] = f"Bearer {await self._broker.token_for(self._server)}"
        yield request


def _wait_for_code(authorize_url: str, port: int, expected_state: str) -> str:
    """Open the browser at Keycloak and wait for the redirect back to 127.0.0.1:<port>/callback."""
    received: dict[str, str] = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            params = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}
            received.update(params)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Logged in. You can close this tab.")

        def log_message(self, *_: object) -> None:  # keep the terminal quiet
            return

    server = HTTPServer(("127.0.0.1", port), Callback)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    webbrowser.open(authorize_url)
    thread.join(timeout=300)
    server.server_close()
    if received.get("state") != expected_state or "code" not in received:
        raise RuntimeError("login failed or was cancelled")
    return received["code"]
