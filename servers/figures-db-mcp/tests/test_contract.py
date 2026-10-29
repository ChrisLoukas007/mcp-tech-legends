"""MCP contract, no database: what the server advertises and how it answers, using a fake backend."""

from __future__ import annotations

from typing import Any

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer

from figures_db_mcp.backend import FiguresBackend
from figures_db_mcp.config import Settings
from figures_db_mcp.models import FigureProfile, FigureSummary
from figures_db_mcp.server import INFO, register
from mcp_kit.server import create_server
from mcp_kit.testing import acting_as

JOBS = FigureSummary(slug="steve-jobs", name="Steve Jobs", born=1955, died=2011, known_for="Apple")


class FakeBackend(FiguresBackend):
    def __init__(self) -> None:
        super().__init__(dsn="unused", statement_timeout_ms=1)

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    async def search_figures(self, query: str, limit: int) -> list[FigureSummary]:
        return [JOBS] if "jobs" in query.lower() else []

    async def get_figure(self, slug: str) -> FigureProfile:
        if slug != "steve-jobs":
            raise LookupError(slug)
        return FigureProfile(**JOBS.model_dump(), country="United States", bio="...", affiliations=[])


def server() -> MCPServer[Any]:
    return create_server(INFO, Settings(), FakeBackend(), register, with_auth=False)


async def test_list_tools_when_connected_then_five_read_only_tools() -> None:
    with acting_as(["figures:read"]):
        async with Client(server()) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {"search_figures", "get_figure", "list_products", "get_timeline", "compare_figures"}
    for tool in tools.values():
        assert tool.annotations is not None and tool.annotations.read_only_hint, tool.name
        assert tool.description and len(tool.description) > 40, tool.name


async def test_search_figures_when_scope_present_then_structured_result() -> None:
    with acting_as(["figures:read"]):
        async with Client(server()) as client:
            result = await client.call_tool("search_figures", {"query": "jobs"})
    assert not result.is_error
    assert result.structured_content == {"result": [JOBS.model_dump()]}


async def test_get_figure_when_unknown_slug_then_readable_tool_error() -> None:
    with acting_as(["figures:read"]):
        async with Client(server()) as client:
            result = await client.call_tool("get_figure", {"slug": "nobody"})
    assert result.is_error
    assert "search_figures" in result.content[0].text  # type: ignore[union-attr]


async def test_search_figures_when_scope_missing_then_denied() -> None:
    with acting_as(["wiki:read"]):
        async with Client(server()) as client:
            result = await client.call_tool("search_figures", {"query": "jobs"})
    assert result.is_error
    assert "figures:read" in result.content[0].text  # type: ignore[union-attr]


@pytest.mark.parametrize("bad", ["Steve Jobs", "x", "../etc/passwd"])
async def test_get_figure_when_slug_malformed_then_rejected_by_schema(bad: str) -> None:
    with acting_as(["figures:read"]):
        async with Client(server()) as client:
            result = await client.call_tool("get_figure", {"slug": bad})
    assert result.is_error
