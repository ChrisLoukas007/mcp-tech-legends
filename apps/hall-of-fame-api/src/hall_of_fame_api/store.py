"""SQL for the private app. Every query is scoped to the owner, so one user can never read or
change another user's data (IDOR protection), and writes are idempotent by key.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import asyncpg

from hall_of_fame_api.models import Collection, CollectionCreate, CollectionDetail, Note, NoteCreate


class IdempotencyConflict(Exception):
    """The same Idempotency-Key was already used for a different request."""


def request_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class Store:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def list_collections(self, owner: str) -> list[Collection]:
        rows = await self._pool.fetch(
            "SELECT id, name, description, created_at FROM halloffame.collections "
            "WHERE owner = $1 ORDER BY id",
            owner,
        )
        return [Collection(**dict(r)) for r in rows]

    async def get_collection(self, owner: str, collection_id: int) -> CollectionDetail | None:
        row = await self._pool.fetchrow(
            "SELECT id, name, description, created_at FROM halloffame.collections "
            "WHERE id = $1 AND owner = $2",
            collection_id,
            owner,
        )
        if row is None:
            return None
        slugs = await self._pool.fetch(
            "SELECT figure_slug FROM halloffame.collection_items WHERE collection_id = $1 ORDER BY added_at",
            collection_id,
        )
        return CollectionDetail(**dict(row), figure_slugs=[s["figure_slug"] for s in slugs])

    async def create_collection(
        self, owner: str, body: CollectionCreate, key: str
    ) -> tuple[Collection, bool]:
        """Returns (collection, created). A retry with the same key returns the original."""
        digest = request_hash({"owner": owner, **body.model_dump()})
        row = await self._pool.fetchrow(
            """
            INSERT INTO halloffame.collections (owner, name, description, idempotency_key, request_sha256)
            VALUES ($1, $2, $3, $4, $5) ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, name, description, created_at
            """,
            owner, body.name, body.description, key, digest,
        )  # fmt: skip
        if row is not None:
            return Collection(**dict(row)), True
        original = await self._pool.fetchrow(
            "SELECT id, name, description, created_at, request_sha256 FROM halloffame.collections "
            "WHERE idempotency_key = $1 AND owner = $2",
            key, owner,
        )  # fmt: skip
        if original is None or original["request_sha256"] != digest:
            raise IdempotencyConflict(key)
        return Collection(**{k: v for k, v in dict(original).items() if k != "request_sha256"}), False

    async def add_item(self, owner: str, collection_id: int, figure_slug: str) -> CollectionDetail | None:
        if await self.get_collection(owner, collection_id) is None:
            return None
        await self._pool.execute(
            "INSERT INTO halloffame.collection_items (collection_id, figure_slug) VALUES ($1, $2) "
            "ON CONFLICT DO NOTHING",
            collection_id, figure_slug,
        )  # fmt: skip
        return await self.get_collection(owner, collection_id)

    async def list_notes(self, owner: str, figure_slug: str | None) -> list[Note]:
        rows = await self._pool.fetch(
            "SELECT id, figure_slug, body, created_at FROM halloffame.notes "
            "WHERE owner = $1 AND ($2::text IS NULL OR figure_slug = $2) ORDER BY id DESC LIMIT 50",
            owner, figure_slug,
        )  # fmt: skip
        return [Note(**dict(r)) for r in rows]

    async def create_note(self, owner: str, body: NoteCreate, key: str) -> tuple[Note, bool]:
        digest = request_hash({"owner": owner, **body.model_dump()})
        row = await self._pool.fetchrow(
            """
            INSERT INTO halloffame.notes (owner, figure_slug, body, idempotency_key, request_sha256)
            VALUES ($1, $2, $3, $4, $5) ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, figure_slug, body, created_at
            """,
            owner, body.figure_slug, body.body, key, digest,
        )  # fmt: skip
        if row is not None:
            return Note(**dict(row)), True
        original = await self._pool.fetchrow(
            "SELECT id, figure_slug, body, created_at, request_sha256 FROM halloffame.notes "
            "WHERE idempotency_key = $1 AND owner = $2",
            key, owner,
        )  # fmt: skip
        if original is None or original["request_sha256"] != digest:
            raise IdempotencyConflict(key)
        return Note(**{k: v for k, v in dict(original).items() if k != "request_sha256"}), False
