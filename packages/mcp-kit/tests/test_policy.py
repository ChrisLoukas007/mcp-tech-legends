"""run_with_policy: scope and role checks, hidden crashes, and one audit record per call."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.server.mcpserver.exceptions import ToolError

from mcp_kit.audit import AuditEvent, fingerprint
from mcp_kit.policy import PermissionDenied, Policy, Principal, run_with_policy


class MemoryAuditSink:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def record(self, event: AuditEvent) -> None:
        self.events.append(event)


@contextmanager
def acting_as(scopes: list[str], roles: list[str] | None = None) -> Iterator[None]:
    token = AccessToken(
        token="t", client_id="test", scopes=scopes, subject="ada", claims={"roles": roles or []}
    )
    reset = auth_context_var.set(AuthenticatedUser(token))
    try:
        yield
    finally:
        auth_context_var.reset(reset)


@pytest.fixture
def sink() -> MemoryAuditSink:
    return MemoryAuditSink()


@pytest.fixture
def policy(sink: MemoryAuditSink) -> Policy:
    return Policy(server="test-mcp", audit=sink)


async def _ok(who: Principal) -> str:
    return f"hello {who.subject}"


async def test_run_with_policy_when_scope_present_then_runs_and_audits_ok(
    policy: Policy, sink: MemoryAuditSink
) -> None:
    with acting_as(["wiki:read"]):
        assert await run_with_policy(policy, "op", "wiki:read", {"q": "x"}, _ok) == "hello ada"
    assert [e.outcome for e in sink.events] == ["ok"]
    assert sink.events[0].args_sha256 == fingerprint({"q": "x"})


async def test_run_with_policy_when_scope_missing_then_denied_and_audited(
    policy: Policy, sink: MemoryAuditSink
) -> None:
    with acting_as(["figures:read"]), pytest.raises(PermissionDenied, match="wiki:read"):
        await run_with_policy(policy, "op", "wiki:read", {}, _ok)
    assert [e.outcome for e in sink.events] == ["denied"]


async def test_run_with_policy_when_role_missing_then_denied(policy: Policy) -> None:
    with (
        acting_as(["halloffame:write"], roles=["legends-viewer"]),
        pytest.raises(PermissionDenied, match="curator"),
    ):
        await run_with_policy(policy, "op", "halloffame:write", {}, _ok, required_role="legends-curator")


async def test_run_with_policy_when_handler_crashes_then_details_hidden(
    policy: Policy, sink: MemoryAuditSink
) -> None:
    async def boom(_: Principal) -> str:
        raise RuntimeError("password=hunter2 leaked in a stack trace")

    with acting_as(["wiki:read"]), pytest.raises(ToolError) as exc_info:
        await run_with_policy(policy, "op", "wiki:read", {}, boom)
    assert "hunter2" not in str(exc_info.value)
    assert "reference" in str(exc_info.value)
    assert [e.outcome for e in sink.events] == ["crash"]


def test_fingerprint_when_key_order_differs_then_same_hash() -> None:
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})
