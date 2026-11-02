"""Step 6 of 6, entry point: HOW it all starts.

`uv run figures-db-mcp` runs main() (wired in pyproject.toml under [project.scripts]).
main() builds the parts and hands them to the shared kit:
    Settings (config.py) + FiguresBackend (backend.py) + INFO, register (server.py) -> serve()
serve() adds auth, audit, logs, metrics and traces, then runs over stdio (the default)
or HTTP (FIGURES_DB_MCP_TRANSPORT=http).
"""

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
