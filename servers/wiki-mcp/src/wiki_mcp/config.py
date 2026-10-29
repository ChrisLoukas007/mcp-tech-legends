"""Settings for wiki-mcp, read from WIKI_MCP_* environment variables."""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from mcp_kit.settings import ServerSettings


class Settings(ServerSettings):
    model_config = SettingsConfigDict(env_prefix="WIKI_MCP_", extra="ignore")

    port: int = 8103
    audience: str = "wiki-mcp"
    public_url: str = "http://localhost:8103/mcp"

    # Outbound HTTP safety
    allowed_upstream_hosts: tuple[str, ...] = ("en.wikipedia.org", "www.wikidata.org")
    timeout_seconds: float = 5.0
    max_response_bytes: int = 1_000_000
    max_concurrent_requests: int = 4
    cache_ttl_seconds: int = 600
    # Wikimedia asks every client to identify itself with a contact (User-Agent policy).
    user_agent: str = "mcp-tech-legends/0.1 (learning project; set WIKI_MCP_USER_AGENT to add your contact)"
