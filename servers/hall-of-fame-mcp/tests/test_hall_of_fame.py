"""hall-of-fame-mcp without Docker: a mock transport plays Keycloak and the private API, so the
tests can check exactly what this server sends downstream."""

from __future__ import annotations

from typing import Any

import httpx2
from mcp import Client
from mcp.server.mcpserver import MCPServer
from pydantic import SecretStr

from hall_of_fame_mcp.backend import HallOfFameClient
from hall_of_fame_mcp.config import Settings
from hall_of_fame_mcp.server import INFO, make_register
from mcp_kit.server import create_server
from mcp_kit.testing import acting_as

CURATOR = ["legends-viewer", "legends-curator"]
NOTE = {"id": 7, "figure_slug": "grace-hopper", "body": "Compilers!", "created_at": "2026-10-29T10:00:00Z"}


class FakeDownstream:
    def __init__(self, api_status: int = 200) -> None:
        self.requests: list[httpx2.Request] = []
        self.token_requests = 0
        self.api_status = api_status

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/token"):
            self.token_requests += 1
            return httpx2.Response(200, json={"access_token": "service-token", "expires_in": 300})
        self.requests.append(request)
        if self.api_status != 200:
            return httpx2.Response(self.api_status, json={"detail": "x"})
        if request.url.path == "/collections":
            return httpx2.Response(200, json=[])
        if request.url.path == "/notes" and request.method == "POST":
            return httpx2.Response(201, json=NOTE)
        return httpx2.Response(404, json={"detail": "not found"})


def server(fake: FakeDownstream) -> MCPServer[Any]:
    settings = Settings(client_secret=SecretStr("test-secret"))
    api = HallOfFameClient(settings, transport=httpx2.MockTransport(fake))
    return create_server(INFO, settings, api, make_register(settings.write_role), with_auth=False)


async def test_list_collections_when_called_then_service_token_and_acting_user_sent() -> None:
    fake = FakeDownstream()
    with acting_as(["halloffame:read"], subject="ada"):
        async with Client(server(fake)) as client:
            await client.call_tool("list_collections", {})
            await client.call_tool("list_collections", {})
    sent = fake.requests[0].headers
    assert sent["authorization"] == "Bearer service-token"  # its own token, not the user's
    assert sent["x-acting-user"] == "ada"
    assert fake.token_requests == 1  # cached between calls


async def test_add_note_when_curator_then_idempotency_key_forwarded() -> None:
    fake = FakeDownstream()
    args = {"figure_slug": "grace-hopper", "body": "Compilers!", "idempotency_key": "note-12345678"}
    with acting_as(["halloffame:write"], roles=CURATOR, subject="ada"):
        async with Client(server(fake)) as client:
            result = await client.call_tool("add_note", args)
    assert not result.is_error
    assert fake.requests[0].headers["idempotency-key"] == "note-12345678"


async def test_add_note_when_viewer_then_denied_before_api_call() -> None:
    fake = FakeDownstream()
    args = {"figure_slug": "grace-hopper", "body": "Compilers!", "idempotency_key": "note-12345678"}
    with acting_as(["halloffame:write"], roles=["legends-viewer"], subject="linus"):
        async with Client(server(fake)) as client:
            result = await client.call_tool("add_note", args)
    assert result.is_error and "legends-curator" in result.content[0].text  # type: ignore[union-attr]
    assert fake.requests == []


async def test_get_collection_when_missing_then_readable_error() -> None:
    with acting_as(["halloffame:read"]):
        async with Client(server(FakeDownstream())) as client:
            result = await client.call_tool("get_collection", {"collection_id": 999})
    assert result.is_error and "list_collections" in result.content[0].text  # type: ignore[union-attr]


async def test_list_collections_when_api_down_then_unavailable_without_details() -> None:
    with acting_as(["halloffame:read"]):
        async with Client(server(FakeDownstream(api_status=500))) as client:
            result = await client.call_tool("list_collections", {})
    assert result.is_error and "unavailable" in result.content[0].text  # type: ignore[union-attr]
