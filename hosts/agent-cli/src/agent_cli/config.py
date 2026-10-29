"""Settings for the host, read from AGENT_CLI_* environment variables."""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_CLI_", extra="ignore")

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

    issuer_url: str = "http://localhost:8180/realms/legends"
    client_id: str = "agent-cli"
    redirect_port: int = 8765

    otlp_endpoint: str | None = None
