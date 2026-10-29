"""Settings every MCP server shares. Each server subclasses this with its own env prefix.

    class Settings(ServerSettings):
        model_config = SettingsConfigDict(env_prefix="WIKI_MCP_")

so `WIKI_MCP_PORT=8103` configures only that server.
"""

from __future__ import annotations

from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # Transport: stdio for a local host (Claude Code), http for remote hosts.
    transport: Literal["stdio", "http"] = "stdio"
    host: str = "127.0.0.1"
    port: int = 8100
    allowed_hosts: list[str] = ["localhost:*", "127.0.0.1:*"]

    # OAuth 2.1 resource server (http only). Each server has its OWN audience.
    issuer_url: str = "http://localhost:8180/realms/legends"
    jwks_url: str | None = None
    audience: str = "change-me"
    public_url: str = "http://localhost:8100/mcp"

    # stdio has no bearer token, so the local developer's identity is configured here.
    stdio_subject: str = "local-developer"
    stdio_scopes: list[str] = []
    stdio_roles: list[str] = []

    # Observability
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    otlp_endpoint: str | None = None  # e.g. http://localhost:4318 (Tempo)
    audit_database_url: SecretStr | None = None  # INSERT-only role on audit.events

    @property
    def resolved_jwks_url(self) -> str:
        return self.jwks_url or f"{self.issuer_url}/protocol/openid-connect/certs"
