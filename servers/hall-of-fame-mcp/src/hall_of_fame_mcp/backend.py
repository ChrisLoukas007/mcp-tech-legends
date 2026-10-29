"""REST client for the private hall-of-fame-api. No MCP imports.

How this server authenticates downstream (the most important idea in this file):
    - It NEVER forwards the user's MCP token to the API (token passthrough is forbidden by the
      MCP spec: that token's audience is this server, not the API).
    - It gets ITS OWN token from Keycloak with client credentials (aud=hall-of-fame-api),
      caches it until shortly before expiry, and sends the verified user in X-Acting-User.

Error mapping: 404 -> LookupError, 409 -> Conflict, 422 -> ValueError, anything else -> UpstreamUnavailable.
"""

from __future__ import annotations

import time
from typing import Any

import httpx2
from opentelemetry.propagate import inject

from hall_of_fame_mcp.config import Settings
from hall_of_fame_mcp.models import Collection, CollectionDetail, Note

TOKEN_REFRESH_MARGIN_SECONDS = 30


class Conflict(Exception):
    """The API refused because of a conflicting earlier request (duplicate name, reused key)."""


class UpstreamUnavailable(Exception):
    """The private API or Keycloak could not be reached or answered with an error."""


class HallOfFameClient:
    def __init__(self, settings: Settings, transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        self._transport = transport
        self._http: httpx2.AsyncClient | None = None
        self._token: str | None = None
        self._token_expires_at = 0.0

    async def start(self) -> None:
        self._http = httpx2.AsyncClient(timeout=self._settings.timeout_seconds, transport=self._transport)

    async def stop(self) -> None:
        if self._http is not None:
            await self._http.aclose()

    async def ready(self) -> bool:
        try:
            return (await self.http.get(f"{self._settings.api_url}/healthz")).status_code == 200
        except httpx2.HTTPError:
            return False

    @property
    def http(self) -> httpx2.AsyncClient:
        if self._http is None:
            raise RuntimeError("http client not started")
        return self._http

    # --- API operations ---------------------------------------------------------------

    async def list_collections(self, user: str) -> list[Collection]:
        return [Collection(**c) for c in await self._call("GET", "/collections", user)]

    async def get_collection(self, user: str, collection_id: int) -> CollectionDetail:
        return CollectionDetail(**await self._call("GET", f"/collections/{collection_id}", user))

    async def create_collection(self, user: str, name: str, description: str, key: str) -> Collection:
        body = {"name": name, "description": description}
        return Collection(**await self._call("POST", "/collections", user, json=body, idempotency_key=key))

    async def add_figure(self, user: str, collection_id: int, figure_slug: str) -> CollectionDetail:
        return CollectionDetail(
            **await self._call("PUT", f"/collections/{collection_id}/items/{figure_slug}", user)
        )

    async def list_notes(self, user: str, figure_slug: str | None) -> list[Note]:
        params = {"figure_slug": figure_slug} if figure_slug else None
        return [Note(**n) for n in await self._call("GET", "/notes", user, params=params)]

    async def add_note(self, user: str, figure_slug: str, body: str, key: str) -> Note:
        payload = {"figure_slug": figure_slug, "body": body}
        return Note(**await self._call("POST", "/notes", user, json=payload, idempotency_key=key))

    # --- plumbing ---------------------------------------------------------------------

    async def _call(
        self,
        method: str,
        path: str,
        user: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        headers = {"Authorization": f"Bearer {await self._service_token()}", "X-Acting-User": user}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        inject(headers)  # W3C traceparent: the API's spans join the same trace
        try:
            response = await self.http.request(
                method, f"{self._settings.api_url}{path}", json=json, params=params, headers=headers
            )
        except httpx2.HTTPError as exc:
            raise UpstreamUnavailable(type(exc).__name__) from exc
        if response.status_code == 404:
            raise LookupError(path)
        if response.status_code == 409:
            raise Conflict(response.json().get("detail", "conflict"))
        if response.status_code == 422:
            raise ValueError("the private API rejected the input")
        if response.status_code >= 300:
            raise UpstreamUnavailable(f"HTTP {response.status_code}")
        return response.json()

    async def _service_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at - TOKEN_REFRESH_MARGIN_SECONDS:
            return self._token
        try:
            response = await self.http.post(
                self._settings.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._settings.client_id,
                    "client_secret": self._settings.client_secret.get_secret_value(),
                },
            )
        except httpx2.HTTPError as exc:
            raise UpstreamUnavailable("identity provider unreachable") from exc
        if response.status_code != 200:
            raise UpstreamUnavailable(f"service token request failed: HTTP {response.status_code}")
        data = response.json()
        self._token = str(data["access_token"])
        self._token_expires_at = time.monotonic() + int(data.get("expires_in", 60))
        return self._token
