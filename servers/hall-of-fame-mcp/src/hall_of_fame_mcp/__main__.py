"""Entry point: `uv run hall-of-fame-mcp` (stdio by default, HALL_OF_FAME_MCP_TRANSPORT=http for HTTP)."""

from __future__ import annotations

from hall_of_fame_mcp.backend import HallOfFameClient
from hall_of_fame_mcp.config import Settings
from hall_of_fame_mcp.server import INFO, make_register
from mcp_kit.server import serve


def main() -> None:
    settings = Settings()
    if not settings.client_secret.get_secret_value():
        raise SystemExit("hall-of-fame-mcp: set HALL_OF_FAME_MCP_CLIENT_SECRET (its Keycloak client secret).")
    serve(INFO, settings, HallOfFameClient(settings), make_register(settings.write_role))


if __name__ == "__main__":
    main()
