"""The MCP layer for wiki-mcp: three read-only tools over Wikipedia and Wikidata."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from mcp_kit.policy import Policy, Principal, run_with_policy
from wiki_mcp.backend import UpstreamUnavailable, WikiBackend
from wiki_mcp.models import SearchResults, Summary, WikidataFacts

SCOPE = "wiki:read"
# open_world_hint=True: these tools reach outside the organisation, to the public internet.
WEB_READ = ToolAnnotations(read_only_hint=True, open_world_hint=True)


def safely[T](call: Callable[[], Awaitable[T]], what: str) -> Callable[[Principal], Awaitable[T]]:
    """Turn backend exceptions into messages the model can act on."""

    async def handler(_who: Principal) -> T:
        try:
            return await call()
        except LookupError:
            raise ToolError(f"No {what} found. Try search_wikipedia to find the exact title.") from None
        except UpstreamUnavailable:
            raise ToolError("Wikipedia/Wikidata is unavailable right now. Try again later.") from None
        except PermissionError:
            raise ToolError("That request was blocked by the server's outbound allow-list.") from None

    return handler


def register_tools(server: MCPServer[Any], backend: WikiBackend, policy: Policy) -> None:
    @server.tool(annotations=WEB_READ)
    async def search_wikipedia(
        query: Annotated[str, Field(min_length=2, max_length=100)],
        limit: Annotated[int, Field(ge=1, le=10)] = 5,
    ) -> SearchResults:
        """Search English Wikipedia. Use it to find the exact article title for a person or
        product before calling get_wikipedia_summary. Returns titles with short snippets."""
        return await run_with_policy(
            policy, "search_wikipedia", SCOPE, {"query": query, "limit": limit},
            safely(lambda: backend.search(query, limit), "results"),
        )  # fmt: skip

    @server.tool(annotations=WEB_READ)
    async def get_wikipedia_summary(title: Annotated[str, Field(min_length=1, max_length=200)]) -> Summary:
        """The lead summary of one Wikipedia article, plus its Wikidata id and URL. Use it to
        check or add to facts from the figures database. The text is public web content."""
        return await run_with_policy(
            policy, "get_wikipedia_summary", SCOPE, {"title": title},
            safely(lambda: backend.summary(title), f"Wikipedia article titled '{title}'"),
        )  # fmt: skip

    @server.tool(annotations=WEB_READ)
    async def get_wikidata_facts(
        entity_id: Annotated[
            str, Field(pattern=r"^Q[1-9][0-9]{0,9}$", description="Wikidata id, e.g. Q19837")
        ],
    ) -> WikidataFacts:
        """Structured facts from Wikidata for one entity: birth/death date, citizenship,
        employers, notable works, awards. Get the id from get_wikipedia_summary (wikidata_id)."""
        return await run_with_policy(
            policy, "get_wikidata_facts", SCOPE, {"entity_id": entity_id},
            safely(lambda: backend.wikidata_facts(entity_id), f"Wikidata entity {entity_id}"),
        )  # fmt: skip
