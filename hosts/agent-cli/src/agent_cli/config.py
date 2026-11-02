"""Step 1 of 5, config: WHICH model, WHICH servers, and HOW to reach them.

Every field can be overridden by an environment variable with the AGENT_CLI_ prefix,
e.g. AGENT_CLI_TRANSPORT=http. Dict fields take JSON, e.g. AGENT_CLI_HTTP_SERVERS='{"wiki": "..."}'.

Next: connections.py (connect to the servers and merge their tools).
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_CLI_", extra="ignore")

    # The LLM side: which Claude model, how hard it thinks, and a cap on tool round trips per
    # question (stops a model that keeps calling tools without ever answering).
    model: str = "claude-opus-5-5"
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    max_tool_rounds: int = 12

    # stdio: launch the servers listed in .mcp.json (same file Claude Code reads).
    # http:  connect to running servers, with one OAuth token per server.
    transport: Literal["stdio", "http"] = "stdio"
    mcp_config: str = ".mcp.json"
    http_servers: dict[str, str] = {
        "figures-db": "http://localhost:8101/mcp",
        "hall-of-fame": "http://localhost:8102/mcp",
        "wiki": "http://localhost:8103/mcp",
    }
    # The scopes to request for each server. Each scope maps to that server's audience in Keycloak.
    server_scopes: dict[str, str] = {
        "figures-db": "figures:read",
        "hall-of-fame": "halloffame:read halloffame:write",
        "wiki": "wiki:read",
    }

    # HTTP mode login: the Keycloak realm, this app's client id, and the local port the browser
    # is redirected back to after login (auth.py).
    issuer_url: str = "http://localhost:8180/realms/legends"
    client_id: str = "agent-cli"
    redirect_port: int = 8765

    # Where to send trace spans (Tempo). None: tracing is off.
    otlp_endpoint: str | None = None
