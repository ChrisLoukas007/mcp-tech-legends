"""Entry point: `uv run hall-of-fame-api`."""

from __future__ import annotations

import uvicorn

from hall_of_fame_api.app import create_app
from hall_of_fame_api.config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
