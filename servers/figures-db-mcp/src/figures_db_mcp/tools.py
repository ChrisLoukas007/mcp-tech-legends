"""Step 4 of 6, tools: WHAT the model may ask for. Thin on purpose.

Each tool has three parts:
    1. typed parameters with limits (Annotated + Field): they become the JSON Schema the model
       sees, and bad input is rejected before our code runs
    2. a docstring written FOR THE MODEL: when to use the tool and what it returns
    3. one call through run_with_policy (scope check, audit, safe errors) to the backend

Tools never contain SQL; they only validate, describe and delegate.

Next: server.py (the server's identity, resources and prompt).
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from figures_db_mcp.backend import FiguresBackend
from figures_db_mcp.models import Comparison, FigureProfile, FigureSummary, Milestone, Product
from mcp_kit.policy import Policy, run_with_policy

# The caller's token (or stdio identity) must carry this scope to use any tool here.
SCOPE = "figures:read"
# Hints for the host: these tools change nothing and only touch our own database.
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)

# Shared input type for every slug parameter: lowercase letters, digits and dashes only.
Slug = Annotated[
    str, Field(pattern=r"^[a-z0-9-]{2,60}$", description="Figure slug from search_figures, e.g. steve-jobs")
]


# Errors are results: tell the model what went wrong AND what to do next.
def not_found(kind: str, key: str) -> ToolError:
    return ToolError(f"No {kind} found for '{key}'. Use search_figures to find valid slugs.")


def register_tools(server: MCPServer[Any], backend: FiguresBackend, policy: Policy) -> None:
    @server.tool(annotations=READ_ONLY)
    async def search_figures(
        query: Annotated[
            str, Field(min_length=2, max_length=60, description="Part of a name or achievement")
        ],
        limit: Annotated[int, Field(ge=1, le=25)] = 10,
    ) -> list[FigureSummary]:
        """Find tech figures by name or what they are known for. Use this first to get a slug.
        Returns up to `limit` figures with slug, name, birth/death year and what they are known for."""
        return await run_with_policy(
            policy,
            "search_figures",
            SCOPE,
            {"query": query, "limit": limit},
            lambda _who: backend.search_figures(query, limit),
        )

    @server.tool(annotations=READ_ONLY)
    async def get_figure(slug: Slug) -> FigureProfile:
        """Full profile of one figure: biography, country and the organisations they worked at."""

        # The handler runs only if the policy allows the call; `_who` is the verified caller.
        async def handler(_who: object) -> FigureProfile:
            try:
                return await backend.get_figure(slug)
            except LookupError:
                raise not_found("figure", slug) from None

        return await run_with_policy(policy, "get_figure", SCOPE, {"slug": slug}, handler)

    @server.tool(annotations=READ_ONLY)
    async def list_products(
        figure_slug: Slug | None = None,
        organization_slug: Annotated[str | None, Field(pattern=r"^[a-z0-9-]{2,60}$")] = None,
        from_year: Annotated[int, Field(ge=1800, le=2100)] = 1800,
        to_year: Annotated[int, Field(ge=1800, le=2100)] = 2100,
        limit: Annotated[int, Field(ge=1, le=50)] = 25,
    ) -> list[Product]:
        """Products, languages, papers and machines, oldest first. Filter by the figure who led
        them, the organisation that made them, and/or a year range."""
        args = {
            "figure_slug": figure_slug,
            "organization_slug": organization_slug,
            "from_year": from_year,
            "to_year": to_year,
            "limit": limit,
        }
        return await run_with_policy(
            policy,
            "list_products",
            SCOPE,
            args,
            lambda _who: backend.list_products(figure_slug, organization_slug, from_year, to_year, limit),
        )

    @server.tool(annotations=READ_ONLY)
    async def get_timeline(slug: Slug) -> list[Milestone]:
        """Dated milestones of one figure's life and work, oldest first."""

        async def handler(_who: object) -> list[Milestone]:
            try:
                return await backend.get_timeline(slug)
            except LookupError:
                raise not_found("figure", slug) from None

        return await run_with_policy(policy, "get_timeline", SCOPE, {"slug": slug}, handler)

    @server.tool(annotations=READ_ONLY)
    async def compare_figures(
        slugs: Annotated[list[Slug], Field(min_length=2, max_length=4)],
    ) -> list[Comparison]:
        """Side-by-side facts for 2 to 4 figures: birth year, first product and year, number of
        products, organisations. Use for "compare X and Y" questions."""

        async def handler(_who: object) -> list[Comparison]:
            try:
                return await backend.compare_figures(slugs)
            except LookupError as exc:
                raise not_found("figure", str(exc)) from None

        return await run_with_policy(policy, "compare_figures", SCOPE, {"slugs": slugs}, handler)
