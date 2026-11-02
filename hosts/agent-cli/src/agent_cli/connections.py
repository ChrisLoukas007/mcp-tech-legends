"""Step 2 of 5, connections: HOW the host connects to every server and builds one tool list.

Many Servers look like One.

This is what a host does before the model sees anything:
    1. open one MCP client per server (stdio subprocess or Streamable HTTP)
    2. tools/list on each, and prefix every name with its server: "wiki__get_wikipedia_summary"
       (two servers may both have a tool called "search"; the prefix keeps them apart)
    3. keep a route from each prefixed name back to (client, original name)

Think of ToolRegistry as a switchboard: the model asks for a tool by its prefixed name, and the
registry forwards the call to the right server under the tool's real name.
A failed call comes back as a ToolOutcome with is_error=True, never as an exception, so one
broken server cannot end the conversation.

Next: loop.py (the model/tool round trips).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncGenerator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx2
from mcp import Client
from mcp.client._transport import TransportStreams
from mcp.client.stdio import StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
from mcp_types import CallToolResult, Tool

SEPARATOR = "__"
# Matches ${VAR} and ${VAR:-default}, the variable syntax used in .mcp.json.
_VAR = re.compile(r"\$\{([^}:]+)(?::-([^}]*))?\}")


# What one tool call gives back to the loop: text for the model, and whether it failed.
@dataclass(frozen=True)
class ToolOutcome:
    text: str
    is_error: bool


@dataclass
class ToolRegistry:
    """Every tool from every connected server, under a server-prefixed name."""

    definitions: list[dict[str, Any]] = field(default_factory=list)
    _routes: dict[str, tuple[Client, str]] = field(default_factory=dict)

    # add runs once at startup and builds the list of tools, it's what the model sees.
    def add(self, server: str, client: Client, tools: list[Tool]) -> None:
        for tool in tools:
            name = f"{server}{SEPARATOR}{tool.name}"
            if name in self._routes:
                raise ValueError(f"Duplicate tool name {name!r}; rename the server or the tool.")
            self._routes[name] = (client, tool.name)
            self.definitions.append(
                {"name": name, "description": tool.description or "", "input_schema": tool.input_schema}
            )

    # call runs every time the model asks for a tool, and sends the requested tool to the right server,
    # it's what the host uses to route calls.
    async def call(self, name: str, arguments: Mapping[str, Any]) -> ToolOutcome:
        if name not in self._routes:
            return ToolOutcome(f"Unknown tool {name!r}.", is_error=True)
        client, tool = self._routes[name]
        try:
            result = await client.call_tool(tool, dict(arguments))
        except Exception as exc:  # a failed call is a tool error the model can see, not a crash
            return ToolOutcome(f"Tool {name!r} failed: {type(exc).__name__}: {exc}", is_error=True)
        return to_outcome(result)


def to_outcome(result: CallToolResult) -> ToolOutcome:
    """Prefer structured JSON (the tool's output schema); fall back to its text blocks."""
    if result.structured_content is not None and not result.is_error:
        return ToolOutcome(json.dumps(result.structured_content, default=str), is_error=False)
    text = "\n".join(c.text for c in result.content if c.type == "text")
    return ToolOutcome(text or "(no content)", is_error=bool(result.is_error))


def expand(value: str) -> str:
    """Expand ${VAR} and ${VAR:-default} like Claude Code; a missing VAR with no default is an error."""

    def sub(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        if name in os.environ:
            return os.environ[name]
        if default is not None:
            return default
        raise KeyError(f"environment variable {name!r} is not set (needed by .mcp.json)")

    return _VAR.sub(sub, value)


def stdio_servers(config_path: str) -> dict[str, StdioServerParameters]:
    """Read the stdio servers from the same .mcp.json Claude Code reads, expanding ${VAR}.

    Servers start in the config file's directory, as Claude Code starts them in the project root.
    """
    path = Path(config_path).resolve()
    config = json.loads(path.read_text()).get("mcpServers", {})
    return {
        name: StdioServerParameters(
            command=expand(entry["command"]),
            args=[expand(a) for a in entry.get("args", [])],
            env={k: expand(v) for k, v in entry.get("env", {}).items()},
            cwd=path.parent,
        )
        for name, entry in config.items()
        if "command" in entry  # skip http/sse entries; this host reaches those via --transport http
    }


@asynccontextmanager
async def _owned_http_transport(url: str, http: httpx2.AsyncClient) -> AsyncGenerator[TransportStreams, None]:
    """The SDK does not close an http client it was handed, so close it here."""
    async with http, streamable_http_client(url, http_client=http) as streams:
        yield streams


def http_client(url: str, auth: httpx2.Auth) -> Client:
    """Streamable HTTP client whose every request carries this server's own bearer token."""
    http = httpx2.AsyncClient(auth=auth, timeout=httpx2.Timeout(30, read=300))  # SDK default SSE read
    return Client(_owned_http_transport(url, http))


async def list_all_tools(client: Client) -> list[Tool]:
    """tools/list is paginated; follow next_cursor so no page of tools is dropped."""
    page = await client.list_tools()
    tools = list(page.tools)
    while page.next_cursor:
        page = await client.list_tools(cursor=page.next_cursor)
        tools.extend(page.tools)
    return tools


@asynccontextmanager
async def connect_all(clients: Mapping[str, Client]) -> AsyncGenerator[ToolRegistry, None]:
    """Open every client, list its tools, and close them all when the session ends."""
    registry = ToolRegistry()
    async with AsyncExitStack() as stack:
        for server, client in clients.items():
            opened = await stack.enter_async_context(client)
            registry.add(server, opened, await list_all_tools(opened))
        yield registry
