"""End to end over HTTP against the running stack (make up && make test-integration).

Plays the host without a model: real Keycloak logins, one token per server, real servers,
the real private API and Postgres. Checks what matters for security, not wording.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import httpx2
import pytest

from agent_cli.auth import ServerTokenAuth, TokenBroker
from agent_cli.config import Settings
from agent_cli.connections import connect_all, http_client

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("AGENT_CLI_E2E"), reason="make up && make test-integration"),
]
SETTINGS = Settings()
PASSWORDS = {"ada": "dev-only-ada", "linus": "dev-only-linus"}


async def login(user: str) -> TokenBroker:
    broker = TokenBroker(SETTINGS.issuer_url, "agent-cli-test", SETTINGS.server_scopes,
                         client_secret=os.environ["AGENT_CLI_TEST_CLIENT_SECRET"])  # fmt: skip
    await broker.password_login(user, PASSWORDS[user])
    return broker


def clients(broker: TokenBroker):  # type: ignore[no-untyped-def]
    return {
        name: http_client(url, ServerTokenAuth(broker, name)) for name, url in SETTINGS.http_servers.items()
    }


@pytest.mark.parametrize("url", list(SETTINGS.http_servers.values()))
async def test_server_when_no_token_then_401(url: str) -> None:
    async with httpx2.AsyncClient() as http:
        response = await http.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert response.status_code == 401


async def test_server_when_token_for_another_server_then_401() -> None:
    figures_token = await (await login("ada")).token_for("figures-db")
    async with httpx2.AsyncClient() as http:
        response = await http.post(
            SETTINGS.http_servers["wiki"],
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={
                "Authorization": f"Bearer {figures_token}",
                "Accept": "application/json, text/event-stream",
            },
        )
    assert response.status_code == 401


async def test_curator_when_saving_note_twice_then_one_note_and_audited() -> None:
    key = f"e2e-{uuid.uuid4().hex[:12]}"
    args = {"figure_slug": "grace-hopper", "body": "Saved over HTTP", "idempotency_key": key}
    async with connect_all(clients(await login("ada"))) as registry:
        found = await registry.call("figures-db__search_figures", {"query": "hopper"})
        first = await registry.call("hall-of-fame__add_note", args)
        again = await registry.call("hall-of-fame__add_note", args)
    assert not found.is_error and "grace-hopper" in found.text
    assert not first.is_error and first.text == again.text

    admin = await asyncpg.connect(os.environ["POSTGRES_ADMIN_URL"])
    try:
        notes = await admin.fetchval("SELECT count(*) FROM halloffame.notes WHERE idempotency_key = $1", key)
        audited = await admin.fetchval(
            "SELECT count(*) FROM audit.events WHERE subject = 'ada' AND operation = 'add_note' "
            "AND occurred_at > now() - interval '1 minute'"
        )
    finally:
        await admin.close()
    assert notes == 1
    assert audited >= 2


async def test_viewer_when_saving_note_then_denied() -> None:
    args = {"figure_slug": "grace-hopper", "body": "Should not be saved", "idempotency_key": "e2e-denied-01"}
    async with connect_all(clients(await login("linus"))) as registry:
        outcome = await registry.call("hall-of-fame__add_note", args)
        listed = await registry.call("hall-of-fame__list_collections", {})
    assert outcome.is_error and "legends-curator" in outcome.text
    assert not listed.is_error and "Open source" in listed.text  # reads still work for viewers
