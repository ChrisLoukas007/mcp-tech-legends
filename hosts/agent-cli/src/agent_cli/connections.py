"""What a host does before the model sees anything: connect to every server and build one
tool list.

    1. open one MCP client per server (stdio subprocess or Streamable HTTP)
    2. tools/list on each, and prefix every name with its server: "wiki__get_wikipedia_summary"
       (two servers may both have a tool called "search"; the prefix keeps them apart)
    3. keep a route from each prefixed name back to (client, original name)
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx2
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
from mcp_types import CallToolResult, Tool

SEPARATOR = "__"


@dataclass(frozen=True)
class ToolOutcome:
    text: str
    is_error: bool


@dataclass
class ToolRegistry:
    """Every tool from every connected server, under a server-prefixed name."""

    definitions: list[dict[str, Any]] = field(default_factory=list)
    _routes: dict[str, tuple[Client, str]] = field(default_factory=dict)

    def add(self, server: str, client: Client, tools: list[Tool]) -> None:
        for tool in tools:
            name = f"{server}{SEPARATOR}{tool.name}"
            self._routes[name] = (client, tool.name)
            self.definitions.append(
                {"name": name, "description": tool.description or "", "input_schema": tool.input_schema}
            )

    async def call(self, name: str, arguments: Mapping[str, Any]) -> ToolOutcome:
        if name not in self._routes:
            return ToolOutcome(f"Unknown tool {name!r}.", is_error=True)
        client, tool = self._routes[name]
        return to_outcome(await client.call_tool(tool, dict(arguments)))


def to_outcome(result: CallToolResult) -> ToolOutcome:
    if result.structured_content is not None and not result.is_error:
        return ToolOutcome(json.dumps(result.structured_content, default=str), is_error=False)
    text = "\n".join(c.text for c in result.content if c.type == "text")
    return ToolOutcome(text or "(no content)", is_error=bool(result.is_error))


def stdio_servers(config_path: str) -> dict[str, StdioServerParameters]:
    """Read the same .mcp.json Claude Code reads, expanding ${VAR} from the environment."""
    config = json.loads(Path(config_path).read_text())["mcpServers"]
    return {
        name: StdioServerParameters(
            command=entry["command"],
            args=entry.get("args", []),
            env={k: os.path.expandvars(v) for k, v in entry.get("env", {}).items()},
        )
        for name, entry in config.items()
    }


def http_client(url: str, auth: httpx2.Auth) -> Client:
    """Streamable HTTP client whose every request carries this server's own bearer token."""
    http = httpx2.AsyncClient(auth=auth, timeout=httpx2.Timeout(30, read=60))
    return Client(streamable_http_client(url, http_client=http))


@asynccontextmanager
async def connect_all(clients: Mapping[str, Client]) -> AsyncIterator[ToolRegistry]:
    """Open every client, list its tools, and close them all when the session ends."""
    registry = ToolRegistry()
    async with AsyncExitStack() as stack:
        for server, client in clients.items():
            opened = await stack.enter_async_context(client)
            registry.add(server, opened, (await opened.list_tools()).tools)
        yield registry
