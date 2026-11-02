"""Step 1 of 6, config: WHERE things are and HOW strict to be.

Every field below can be overridden by an environment variable with the FIGURES_DB_MCP_ prefix,
e.g. FIGURES_DB_MCP_PORT=9000. Settings shared by all servers (transport, auth, logging) come
from mcp_kit.settings.ServerSettings; only what is specific to this server is declared here.

Next: models.py (the shape of each answer).
"""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict

from mcp_kit.settings import ServerSettings


class Settings(ServerSettings):
    model_config = SettingsConfigDict(env_prefix="FIGURES_DB_MCP_", extra="ignore")

    # HTTP mode only: where to listen, which token audience to accept, and the public address.
    port: int = 8101
    audience: str = "figures-db-mcp"
    public_url: str = "http://localhost:8101/mcp"

    # The figures_reader role can only SELECT from the legends schema (infra/postgres/02_roles.sql).
    database_url: SecretStr = SecretStr("postgresql://figures_reader:change-me@localhost:5433/legends")
    # Postgres cancels any query that runs longer than this, so one slow query cannot hang the server.
    statement_timeout_ms: int = 3_000
