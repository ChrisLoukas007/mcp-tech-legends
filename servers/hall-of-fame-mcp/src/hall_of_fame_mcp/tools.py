"""The MCP layer for hall-of-fame-mcp: three read tools and three write tools.

The user acted for is ALWAYS the verified principal (who.subject), never a tool argument: the
model cannot ask to read or write someone else's Hall of Fame.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from hall_of_fame_mcp.backend import Conflict, HallOfFameClient, UpstreamUnavailable
from hall_of_fame_mcp.models import Collection, CollectionDetail, Note
from mcp_kit.policy import Policy, Principal, run_with_policy

READ, WRITE = "halloffame:read", "halloffame:write"
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
ADDITIVE_WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True)

FigureSlug = Annotated[str, Field(pattern=r"^[a-z0-9-]{2,60}$", description="Figure slug, e.g. steve-jobs")]
CollectionId = Annotated[int, Field(ge=1, description="Collection id from list_collections")]
IdempotencyKey = Annotated[
    str,
    Field(
        pattern=r"^[A-Za-z0-9_-]{8,64}$",
        description="Unique key you generate once per intended change (e.g. a UUID). "
        "Reuse the SAME key when retrying; it prevents duplicate writes.",
    ),
]


def as_user[T](call: Callable[[str], Awaitable[T]]) -> Callable[[Principal], Awaitable[T]]:
    """Run the backend call for the verified user and translate failures for the model."""

    async def handler(who: Principal) -> T:
        try:
            return await call(who.subject)
        except LookupError:
            raise ToolError(
                "Not found in your Hall of Fame. Use list_collections to see valid ids."
            ) from None
        except Conflict as exc:
            raise ToolError(f"Refused: {exc}.") from None
        except ValueError as exc:
            raise ToolError(str(exc)) from None
        except UpstreamUnavailable:
            raise ToolError("The Hall of Fame service is unavailable right now. Try again later.") from None

    return handler


def register_tools(server: MCPServer[Any], api: HallOfFameClient, policy: Policy, write_role: str) -> None:
    @server.tool(annotations=READ_ONLY)
    async def list_collections() -> list[Collection]:
        """The current user's Hall of Fame collections (id, name, description)."""
        return await run_with_policy(policy, "list_collections", READ, {}, as_user(api.list_collections))

    @server.tool(annotations=READ_ONLY)
    async def get_collection(collection_id: CollectionId) -> CollectionDetail:
        """One of the current user's collections, with the slugs of the figures in it."""
        return await run_with_policy(
            policy, "get_collection", READ, {"collection_id": collection_id},
            as_user(lambda user: api.get_collection(user, collection_id)),
        )  # fmt: skip

    @server.tool(annotations=READ_ONLY)
    async def list_notes(figure_slug: FigureSlug | None = None) -> list[Note]:
        """The current user's notes, newest first, optionally only about one figure."""
        return await run_with_policy(
            policy, "list_notes", READ, {"figure_slug": figure_slug},
            as_user(lambda user: api.list_notes(user, figure_slug)),
        )  # fmt: skip

    @server.tool(annotations=ADDITIVE_WRITE)
    async def create_collection(
        name: Annotated[str, Field(min_length=2, max_length=80)],
        idempotency_key: IdempotencyKey,
        description: Annotated[str, Field(max_length=500)] = "",
    ) -> Collection:
        """Create a new collection in the current user's Hall of Fame. Needs the curator role.
        Returns the collection (the original one if this is a retry with the same key)."""
        return await run_with_policy(
            policy, "create_collection", WRITE, {"name": name, "description": description},
            as_user(lambda user: api.create_collection(user, name, description, idempotency_key)),
            required_role=write_role,
        )  # fmt: skip

    @server.tool(annotations=ADDITIVE_WRITE)
    async def add_figure_to_collection(
        collection_id: CollectionId, figure_slug: FigureSlug
    ) -> CollectionDetail:
        """Add a figure to one of the current user's collections. Safe to repeat. Needs the curator role."""
        args = {"collection_id": collection_id, "figure_slug": figure_slug}
        return await run_with_policy(
            policy, "add_figure_to_collection", WRITE, args,
            as_user(lambda user: api.add_figure(user, collection_id, figure_slug)),
            required_role=write_role,
        )  # fmt: skip

    @server.tool(annotations=ADDITIVE_WRITE)
    async def add_note(
        figure_slug: FigureSlug,
        body: Annotated[str, Field(min_length=3, max_length=2000)],
        idempotency_key: IdempotencyKey,
    ) -> Note:
        """Save a note about a figure to the current user's Hall of Fame. Needs the curator role.
        Returns the note (the original one if this is a retry with the same key)."""
        return await run_with_policy(
            policy, "add_note", WRITE, {"figure_slug": figure_slug, "body": body},
            as_user(lambda user: api.add_note(user, figure_slug, body, idempotency_key)),
            required_role=write_role,
        )  # fmt: skip
