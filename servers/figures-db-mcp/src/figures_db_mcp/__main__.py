"""Entry point: `uv run figures-db-mcp` (stdio by default, FIGURES_DB_MCP_TRANSPORT=http for HTTP)."""

from __future__ import annotations

from figures_db_mcp.backend import FiguresBackend
from figures_db_mcp.config import Settings
from figures_db_mcp.server import INFO, register
from mcp_kit.server import serve


def main() -> None:
    settings = Settings()
    backend = FiguresBackend(settings.database_url.get_secret_value(), settings.statement_timeout_ms)
    serve(INFO, settings, backend, register)


if __name__ == "__main__":
    main()
