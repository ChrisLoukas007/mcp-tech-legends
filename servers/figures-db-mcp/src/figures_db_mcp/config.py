"""Settings for figures-db-mcp, read from FIGURES_DB_MCP_* environment variables."""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict

from mcp_kit.settings import ServerSettings


class Settings(ServerSettings):
    model_config = SettingsConfigDict(env_prefix="FIGURES_DB_MCP_", extra="ignore")

    port: int = 8101
    audience: str = "figures-db-mcp"
    public_url: str = "http://localhost:8101/mcp"

    # The figures_reader role can only SELECT from the legends schema (infra/postgres/02_roles.sql).
    database_url: SecretStr = SecretStr("postgresql://figures_reader:change-me@localhost:5433/legends")
    statement_timeout_ms: int = 3_000
