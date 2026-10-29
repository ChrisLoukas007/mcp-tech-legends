"""The database side: plain asyncpg, no MCP imports. Every query is parameterised ($1, $2)
and bounded (LIMIT), and the role it runs as can only read (infra/postgres/02_roles.sql).

Not found is raised as LookupError; tools.py turns it into a message the model can act on.
"""

from __future__ import annotations

import asyncpg

from figures_db_mcp.models import (
    Affiliation,
    Comparison,
    FigureProfile,
    FigureSummary,
    Milestone,
    Organization,
    Product,
)

_PRODUCT_SELECT = """
    SELECT p.slug, p.name, p.year, p.category, o.name AS organization, f.name AS lead_figure, p.description
    FROM legends.products p
    LEFT JOIN legends.organizations o ON o.id = p.organization_id
    LEFT JOIN legends.figures f ON f.id = p.lead_figure_id
"""


class FiguresBackend:
    def __init__(self, dsn: str, statement_timeout_ms: int) -> None:
        self._dsn = dsn
        self._timeout_ms = statement_timeout_ms
        self._pool: asyncpg.Pool | None = None

    async def start(self) -> None:
        self._pool = await asyncpg.create_pool(
            self._dsn,
            min_size=1,
            max_size=5,
            command_timeout=self._timeout_ms / 1000,
            server_settings={"statement_timeout": str(self._timeout_ms)},
        )

    async def stop(self) -> None:
        if self._pool is not None:
            await self._pool.close()

    async def ready(self) -> bool:
        try:
            return bool(await self.pool.fetchval("SELECT 1", timeout=2) == 1)
        except (asyncpg.PostgresError, OSError, TimeoutError, RuntimeError):
            return False

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("database pool not started")
        return self._pool

    async def search_figures(self, query: str, limit: int) -> list[FigureSummary]:
        rows = await self.pool.fetch(
            """
            SELECT slug, name, born, died, known_for FROM legends.figures
            WHERE name ILIKE '%' || $1 || '%' OR known_for ILIKE '%' || $1 || '%'
            ORDER BY name LIMIT $2
            """,
            query,
            limit,
        )
        return [FigureSummary(**dict(r)) for r in rows]

    async def get_figure(self, slug: str) -> FigureProfile:
        row = await self.pool.fetchrow("SELECT * FROM legends.figures WHERE slug = $1", slug)
        if row is None:
            raise LookupError(slug)
        affiliations = await self.pool.fetch(
            """
            SELECT o.name AS organization, a.role, a.from_year
            FROM legends.affiliations a JOIN legends.organizations o ON o.id = a.organization_id
            WHERE a.figure_id = $1 ORDER BY a.from_year
            """,
            row["id"],
        )
        data = {k: v for k, v in dict(row).items() if k != "id"}
        return FigureProfile(**data, affiliations=[Affiliation(**dict(a)) for a in affiliations])

    async def list_products(
        self, figure_slug: str | None, organization_slug: str | None, from_year: int, to_year: int, limit: int
    ) -> list[Product]:
        rows = await self.pool.fetch(
            _PRODUCT_SELECT
            + """
            WHERE ($1::text IS NULL OR f.slug = $1) AND ($2::text IS NULL OR o.slug = $2)
              AND p.year BETWEEN $3 AND $4
            ORDER BY p.year LIMIT $5
            """,
            figure_slug,
            organization_slug,
            from_year,
            to_year,
            limit,
        )
        return [Product(**dict(r)) for r in rows]

    async def get_timeline(self, slug: str) -> list[Milestone]:
        rows = await self.pool.fetch(
            """
            SELECT m.year, m.title FROM legends.milestones m JOIN legends.figures f ON f.id = m.figure_id
            WHERE f.slug = $1 ORDER BY m.year, m.id
            """,
            slug,
        )
        if not rows:
            raise LookupError(slug)
        return [Milestone(**dict(r)) for r in rows]

    async def compare_figures(self, slugs: list[str]) -> list[Comparison]:
        rows = await self.pool.fetch(
            """
            SELECT f.slug, f.name, f.born,
                   (SELECT p.name FROM legends.products p WHERE p.lead_figure_id = f.id
                    ORDER BY p.year LIMIT 1) AS first_product,
                   (SELECT min(p.year) FROM legends.products p
                    WHERE p.lead_figure_id = f.id) AS first_product_year,
                   (SELECT count(*) FROM legends.products p WHERE p.lead_figure_id = f.id) AS product_count,
                   COALESCE((SELECT array_agg(o.name ORDER BY a.from_year) FROM legends.affiliations a
                             JOIN legends.organizations o ON o.id = a.organization_id
                             WHERE a.figure_id = f.id), '{}') AS organizations
            FROM legends.figures f WHERE f.slug = ANY($1::text[]) ORDER BY f.born
            """,
            slugs,
        )
        missing = set(slugs) - {r["slug"] for r in rows}
        if missing:
            raise LookupError(", ".join(sorted(missing)))
        return [Comparison(**dict(r)) for r in rows]

    async def list_organizations(self) -> list[Organization]:
        rows = await self.pool.fetch(
            "SELECT slug, name, kind, founded, location FROM legends.organizations ORDER BY name LIMIT 100"
        )
        return [Organization(**dict(r)) for r in rows]
