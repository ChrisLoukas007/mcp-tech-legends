"""Run the custom host.

    uv run agent-cli                                    chat, servers over stdio (from .mcp.json)
    uv run agent-cli --ask "Who founded NVIDIA?"        one question
    AGENT_CLI_TRANSPORT=http uv run agent-cli           servers over HTTP, browser login (PKCE)
    uv run agent-cli --transport http --user linus      HTTP, password login (local test client)

Needs ANTHROPIC_API_KEY (or an `ant auth login` profile) for Claude.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any

from mcp import Client

from agent_cli.auth import ServerTokenAuth, TokenBroker
from agent_cli.config import Settings
from agent_cli.connections import connect_all, http_client, stdio_servers
from agent_cli.loop import ClaudeLlm, run_turn
from mcp_kit.observability import configure_logging, configure_tracing

TEST_USERS = {"ada": "dev-only-ada", "linus": "dev-only-linus"}  # fixtures from infra/keycloak/realm.json


async def build_clients(settings: Settings, user: str | None) -> dict[str, Client]:
    if settings.transport == "stdio":
        return {name: Client(params) for name, params in stdio_servers(settings.mcp_config).items()}
    if user:
        broker = TokenBroker(settings.issuer_url, "agent-cli-test", settings.server_scopes,
                             client_secret=os.environ.get("AGENT_CLI_TEST_CLIENT_SECRET", ""))  # fmt: skip
        await broker.password_login(user, TEST_USERS[user])
    else:
        broker = TokenBroker(settings.issuer_url, settings.client_id, settings.server_scopes)
        await broker.pkce_login(settings.redirect_port)
    return {
        name: http_client(url, ServerTokenAuth(broker, name)) for name, url in settings.http_servers.items()
    }


async def chat(settings: Settings, ask: str | None, user: str | None) -> None:
    llm = ClaudeLlm(settings.model, settings.effort)
    messages: list[dict[str, Any]] = []
    async with connect_all(await build_clients(settings, user)) as registry:
        print(f"connected: {len(registry.definitions)} tools over {settings.transport}", file=sys.stderr)
        questions = [ask] if ask else iter(lambda: input("\nyou> "), "exit")
        for question in questions:
            result = await run_turn(llm, registry, messages, question, settings.max_tool_rounds)
            for call in result.tool_calls:
                print(f"  -> {call}", file=sys.stderr)
            print(f"\nassistant> {result.answer}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tech Legends: a custom MCP host using Claude")
    parser.add_argument("--ask", help="ask one question and exit")
    parser.add_argument("--transport", choices=["stdio", "http"])
    parser.add_argument("--user", choices=sorted(TEST_USERS), help="HTTP only: log in as a test user")
    args = parser.parse_args()
    settings = Settings(**({"transport": args.transport} if args.transport else {}))
    configure_logging("WARNING")
    configure_tracing("agent-cli", settings.otlp_endpoint)
    try:
        asyncio.run(chat(settings, args.ask, args.user))
    except (KeyboardInterrupt, EOFError):
        pass


if __name__ == "__main__":
    main()
