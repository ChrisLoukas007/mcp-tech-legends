"""Step 7 of 7, testing: HOW tests pretend to be a user without Keycloak.

Test helpers shared by every server's tests. `acting_as` puts a fake identity into the same
auth context that auth.py fills in production, so policy.py runs its real checks against it:

    with acting_as(["halloffame:write"], roles=["legends-viewer"], subject="linus"):
        ...  # add_note must be denied: linus lacks the curator role
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken


@contextmanager
def acting_as(scopes: list[str], roles: list[str] | None = None, subject: str = "ada") -> Iterator[None]:
    """Run code as a caller with these scopes and roles, using the SDK's own auth context.
    Set it BEFORE opening an in-process `mcp.Client(server)` so the server task inherits it."""
    token = AccessToken(
        token="test", client_id="test", scopes=scopes, subject=subject, claims={"roles": roles or []}
    )
    reset = auth_context_var.set(AuthenticatedUser(token))
    try:
        yield
    finally:
        auth_context_var.reset(reset)
