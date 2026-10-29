"""Settings for hall-of-fame-mcp, read from HALL_OF_FAME_MCP_* environment variables."""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict

from mcp_kit.settings import ServerSettings


class Settings(ServerSettings):
    model_config = SettingsConfigDict(env_prefix="HALL_OF_FAME_MCP_", extra="ignore")

    port: int = 8102
    audience: str = "hall-of-fame-mcp"
    public_url: str = "http://localhost:8102/mcp"

    # Downstream: the private API, called with THIS server's own credential (client credentials).
    api_url: str = "http://localhost:8200"
    token_url: str = "http://localhost:8180/realms/legends/protocol/openid-connect/token"  # noqa: S105 - a URL
    client_id: str = "hall-of-fame-mcp"
    client_secret: SecretStr = SecretStr("")
    timeout_seconds: float = 5.0

    # Writes need the user to be a curator, not only the app to hold halloffame:write.
    write_role: str = "legends-curator"
