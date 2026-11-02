"""Step 4 of 7, policy: WHO may do WHAT. The most important file in the repo.

Policy enforcement point: every tool call and resource read in every server goes through
`run_with_policy`, so no tool can forget authorisation, audit, metrics or error hiding.
Think of a security guard at one door that every request must pass.

    principal -> scope (+ role) check -> handler -> error mapping -> metrics + audit

principal  the verified caller (subject, scopes, roles), read from the SDK's auth context,
           which auth.py fills from the token (HTTP) or set_stdio_principal fills (stdio)
handler    the tool's real work, passed in as a function and run ONLY after the check passes

Two kinds of permission, both must pass:
    scope  what the APP was allowed to ask for (in the token, from the OAuth client)
    role   what the USER is allowed to do (realm roles in the token)

Every outcome is one of: ok, denied, error (a ToolError the model may read), crash (anything
else: logged in full here, shown to the model only as a reference id).

Next: auth.py (how the token behind the principal is checked).
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from mcp.server.auth.middleware.auth_context import auth_context_var, get_access_token
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.server.mcpserver.exceptions import ToolError

from mcp_kit.audit import AuditEvent, AuditSink, fingerprint
from mcp_kit.observability import AUTHZ_DENIED, TOOL_CALLS, TOOL_DURATION

logger = logging.getLogger(__name__)


class NotAuthenticated(ToolError):
    """No verified identity is attached to this request."""


class PermissionDenied(ToolError):
    """The caller is authenticated but lacks the scope or role this operation needs."""


class UpstreamError(ToolError):
    """A backend (database, private API, public API) failed. The model sees only a reference id."""


@dataclass(frozen=True)
class Principal:
    subject: str
    client_id: str
    scopes: frozenset[str]
    roles: frozenset[str]


@dataclass(frozen=True)
class Policy:
    """What one server needs to enforce: its name (for metrics/audit) and where audit goes."""

    server: str
    audit: AuditSink


def current_principal() -> Principal:
    token = get_access_token()
    if token is None:
        raise NotAuthenticated("Not authenticated.")
    claims = token.claims or {}
    return Principal(
        subject=token.subject or token.client_id,
        client_id=token.client_id,
        scopes=frozenset(token.scopes),
        roles=frozenset(claims.get("roles", [])),
    )


def require(principal: Principal, scope: str, role: str | None = None) -> None:
    if scope not in principal.scopes:
        raise PermissionDenied(f"Permission denied: this action needs the '{scope}' scope.")
    if role is not None and role not in principal.roles:
        raise PermissionDenied(f"Permission denied: this action needs the '{role}' role.")


def set_stdio_principal(subject: str, scopes: list[str], roles: list[str]) -> None:
    """stdio has no HTTP layer and no bearer token, so attach the local developer's identity
    to the SDK's own auth context. Authorisation then uses one code path for both transports."""
    token = AccessToken(
        token="stdio-local",  # noqa: S106 - placeholder, not a credential
        client_id="stdio-local",
        scopes=scopes,
        subject=subject,
        claims={"roles": roles},
    )
    auth_context_var.set(AuthenticatedUser(token))


async def run_with_policy[T](
    policy: Policy,
    operation: str,
    required_scope: str,
    args: Mapping[str, Any],
    handler: Callable[[Principal], Awaitable[T]],
    *,
    required_role: str | None = None,
) -> T:
    correlation_id = uuid.uuid4().hex
    started = time.perf_counter()
    principal: Principal | None = None
    outcome, error = "ok", None
    try:
        principal = current_principal()
        require(principal, required_scope, required_role)
        return await handler(principal)
    except (NotAuthenticated, PermissionDenied) as exc:
        outcome, error = "denied", str(exc)
        AUTHZ_DENIED.labels(server=policy.server, operation=operation, scope=required_scope).inc()
        raise
    except ToolError as exc:  # includes UpstreamError raised by backends
        outcome, error = "error", str(exc)
        raise
    except Exception as exc:
        # Unknown failure: log details server-side, show the model only a reference id.
        outcome, error = "crash", type(exc).__name__
        logger.exception("operation failed", extra={"operation": operation, "correlation_id": correlation_id})
        raise UpstreamError(f"The operation failed. Try again later (reference {correlation_id}).") from exc
    finally:
        elapsed = time.perf_counter() - started
        TOOL_CALLS.labels(server=policy.server, operation=operation, outcome=outcome).inc()
        TOOL_DURATION.labels(server=policy.server, operation=operation).observe(elapsed)
        await policy.audit.record(
            AuditEvent(
                server=policy.server,
                correlation_id=correlation_id,
                subject=principal.subject if principal else "anonymous",
                client_id=principal.client_id if principal else "anonymous",
                operation=operation,
                args_sha256=fingerprint(args),
                outcome=outcome,
                duration_ms=int(elapsed * 1000),
                error=error,
            )
        )
