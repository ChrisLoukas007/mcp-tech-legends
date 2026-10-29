"""What hall-of-fame-mcp IS: identity, instructions, tools, one resource and one prompt."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer

from hall_of_fame_mcp import tools
from hall_of_fame_mcp.backend import HallOfFameClient
from mcp_kit.policy import Policy, run_with_policy
from mcp_kit.server import ServerInfo

INFO = ServerInfo(
    name="hall-of-fame-mcp",
    title="My Hall of Fame",
    version="0.1.0",
    instructions=(
        "The current user's private Hall of Fame: collections of tech figures and personal notes.\n"
        "- Writes need an idempotency_key: generate one per intended change, reuse it on retry.\n"
        "- Ask the user before creating or adding anything unless they clearly asked for it.\n"
        "- Figure slugs come from the figures database (search_figures)."
    ),
)


def make_register(write_role: str) -> Callable[[MCPServer[Any], HallOfFameClient, Policy], None]:
    def register(server: MCPServer[Any], api: HallOfFameClient, policy: Policy) -> None:
        tools.register_tools(server, api, policy, write_role)

        @server.resource(
            "halloffame://collections/{collection_id}",
            mime_type="application/json",
            description="One of the current user's collections, with its figures.",
        )
        async def collection_resource(collection_id: str) -> str:
            if not collection_id.isdigit():
                raise ValueError("collection_id must be a positive integer")
            detail = await run_with_policy(
                policy, "resource:collection", tools.READ, {"collection_id": collection_id},
                tools.as_user(lambda user: api.get_collection(user, int(collection_id))),
            )  # fmt: skip
            return detail.model_dump_json()

        @server.prompt(title="Curate a collection")
        def curate_collection(theme: str) -> str:
            """Build a themed collection: find figures, confirm with the user, then save."""
            return (
                f"Help me build a Hall of Fame collection with the theme {theme!r}.\n"
                "1. Use search_figures and compare_figures to propose 3 to 5 figures, one line each on why.\n"
                "2. Wait for my confirmation.\n"
                "3. Then create_collection and add_figure_to_collection for each,\n"
                "   with a fresh idempotency key for the collection."
            )

    return register
