"""Entry point: `uv run wiki-mcp` (stdio by default, WIKI_MCP_TRANSPORT=http for HTTP)."""

from __future__ import annotations

from mcp_kit.server import serve
from wiki_mcp.backend import WikiBackend
from wiki_mcp.config import Settings
from wiki_mcp.server import INFO, register


def main() -> None:
    settings = Settings()
    serve(INFO, settings, WikiBackend(settings), register)


if __name__ == "__main__":
    main()
