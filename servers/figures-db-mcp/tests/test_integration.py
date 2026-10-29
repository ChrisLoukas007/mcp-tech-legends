"""Real SQL against the compose Postgres, as the read-only figures_reader role.

make up && make test-integration
"""

from __future__ import annotations

import os

import asyncpg
import pytest

from figures_db_mcp.backend import FiguresBackend

DSN = os.environ.get("FIGURES_DB_MCP_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DSN, reason="set FIGURES_DB_MCP_DATABASE_URL (make test-integration)"),
]


@pytest.fixture
async def backend():  # type: ignore[no-untyped-def]
    b = FiguresBackend(str(DSN), statement_timeout_ms=3000)
    await b.start()
    yield b
    await b.stop()


async def test_search_figures_when_name_matches_then_found(backend: FiguresBackend) -> None:
    results = await backend.search_figures("jobs", 10)
    assert [r.slug for r in results] == ["steve-jobs"]


async def test_compare_figures_when_two_founders_then_first_products(backend: FiguresBackend) -> None:
    rows = {r.slug: r for r in await backend.compare_figures(["steve-jobs", "bill-gates"])}
    assert rows["bill-gates"].first_product == "Altair BASIC"
    assert rows["steve-jobs"].first_product == "Macintosh"


async def test_list_products_when_filtered_by_year_then_bounded(backend: FiguresBackend) -> None:
    products = await backend.list_products(None, "apple", 1976, 1984, 25)
    assert [p.year for p in products] == sorted(p.year for p in products)
    assert {p.name for p in products} == {"Apple I", "Apple II", "Macintosh"}


async def test_role_when_writing_then_permission_denied(backend: FiguresBackend) -> None:
    with pytest.raises(asyncpg.PostgresError):
        await backend.pool.execute("UPDATE legends.figures SET name = 'x' WHERE slug = 'steve-jobs'")
