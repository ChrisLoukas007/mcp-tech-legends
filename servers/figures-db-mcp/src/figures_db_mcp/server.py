"""Step 5 of 6, server: WHO this server is and everything it offers.

INFO is its identity card: name, version, and instructions sent to the host when it connects
(hosts usually pass them on to the model). register() attaches the three kinds of capability:
    - tools      actions the model calls                 -> tools.py
    - resources  read-only data addressed by a URI       -> below
    - prompts    ready-made workflows the user can pick  -> below
The two resources and one prompt are small, so they live here.

Next: __main__.py (how it all starts).
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from figures_db_mcp import tools
from figures_db_mcp.backend import FiguresBackend
from mcp_kit.policy import Policy, run_with_policy
from mcp_kit.server import ServerInfo

INFO = ServerInfo(
    name="figures-db-mcp",
    title="Tech Legends database",
    version="0.1.0",
    instructions=(
        "Read-only facts about technology pioneers: people, organisations, products, timelines.\n"
        "- Call search_figures first to get a slug, then use the slug with the other tools.\n"
        "- The data is a curated demo set; say so if the user needs authoritative facts."
    ),
)


def register(server: MCPServer[Any], backend: FiguresBackend, policy: Policy) -> None:
    tools.register_tools(server, backend, policy)

    @server.resource(
        "legends://figures/{slug}",
        mime_type="application/json",
        description="Full profile of one figure (same data as the get_figure tool).",
    )
    async def figure_resource(slug: str) -> str:
        async def handler(_who: object) -> str:
            try:
                return (await backend.get_figure(slug)).model_dump_json()
            except LookupError:
                raise tools.not_found("figure", slug) from None

        return await run_with_policy(policy, "resource:figure", tools.SCOPE, {"slug": slug}, handler)

    @server.resource(
        "legends://organizations",
        mime_type="application/json",
        description="All organisations in the database.",
    )
    async def organizations_resource() -> str:
        rows = await run_with_policy(
            policy, "resource:organizations", tools.SCOPE, {}, lambda _who: backend.list_organizations()
        )
        return json.dumps([r.model_dump() for r in rows])

    @server.prompt(title="Profile a tech figure")
    def profile_figure(slug: str) -> str:
        """Standard workflow for writing a short, sourced profile of one figure."""
        if not slug.replace("-", "").isalnum():
            raise ToolError("slug must contain only letters, digits and dashes")
        return (
            f"Write a short profile of the figure with slug '{slug}'.\n"
            f"1. Read the resource legends://figures/{slug}.\n"
            f"2. Call get_timeline for '{slug}' and pick the three most important milestones.\n"
            "3. Call list_products for the same figure.\n"
            "4. Write 5 sentences. Mark anything not found in these results as unverified."
        )
