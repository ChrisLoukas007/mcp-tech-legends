"""Private API: who may call it (unit, no DB) and per-user isolation + idempotency (integration)."""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

import asyncpg
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from hall_of_fame_api.app import create_app, get_store
from hall_of_fame_api.config import Settings
from hall_of_fame_api.models import CollectionCreate, NoteCreate
from hall_of_fame_api.store import IdempotencyConflict, Store

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
SETTINGS = Settings()


def token(**overrides: Any) -> str:
    now = int(time.time())
    claims = {"iss": SETTINGS.issuer_url, "aud": "hall-of-fame-api", "azp": "hall-of-fame-mcp",
              "sub": "svc", "iat": now, "exp": now + 300} | overrides  # fmt: skip
    return jwt.encode(claims, KEY, algorithm="RS256")


class EmptyStore:
    async def list_collections(self, owner: str) -> list[Any]:
        return []


@pytest.fixture
def client() -> TestClient:
    app = create_app(SETTINGS, key_resolver=lambda _t: KEY.public_key())
    app.dependency_overrides[get_store] = EmptyStore
    return TestClient(app)  # no `with`: lifespan (DB pool) does not run


def test_list_collections_when_service_token_and_user_then_ok(client: TestClient) -> None:
    r = client.get("/collections", headers={"Authorization": f"Bearer {token()}", "X-Acting-User": "ada"})
    assert r.status_code == 200 and r.json() == []


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({}, 401),
        ({"Authorization": "Bearer not-a-jwt", "X-Acting-User": "ada"}, 401),
        ({"Authorization": f"Bearer {token(aud='wiki-mcp')}", "X-Acting-User": "ada"}, 401),
        # A user's own token sent straight to the API (token passthrough) is refused.
        ({"Authorization": f"Bearer {token(azp='agent-cli')}", "X-Acting-User": "ada"}, 403),
        ({"Authorization": f"Bearer {token()}"}, 400),
        ({"Authorization": f"Bearer {token()}", "X-Acting-User": "Robert'); DROP TABLE"}, 400),
    ],
)
def test_list_collections_when_caller_not_allowed_then_rejected(
    client: TestClient, headers: dict[str, str], status: int
) -> None:
    assert client.get("/collections", headers=headers).status_code == status


# --- integration: the real store as the halloffame_app role ------------------------------

DSN = os.environ.get("HALL_OF_FAME_API_DATABASE_URL")
TEST_OWNER = "itest-user"  # writes never touch the demo users


def needs_db(test: Any) -> Any:
    return pytest.mark.integration(pytest.mark.skipif(not DSN, reason="make test-integration")(test))


@pytest.fixture
async def store():  # type: ignore[no-untyped-def]
    pool = await asyncpg.create_pool(str(DSN), min_size=1, max_size=2)
    yield Store(pool)
    await pool.close()


@needs_db
async def test_get_collection_when_other_users_then_not_found(store: Store) -> None:
    ada_first = (await store.list_collections("ada"))[0]
    assert await store.get_collection("linus", ada_first.id) is None


@needs_db
async def test_create_note_when_retried_with_same_key_then_one_note(store: Store) -> None:
    key = f"test-{uuid.uuid4().hex[:12]}"
    body = NoteCreate(figure_slug="ada-lovelace", body="Retry-safe note")
    first, created = await store.create_note(TEST_OWNER, body, key)
    again, created_again = await store.create_note(TEST_OWNER, body, key)
    assert created and not created_again and first.id == again.id


@needs_db
async def test_create_note_when_other_owner_used_same_key_then_both_saved(store: Store) -> None:
    key = f"test-{uuid.uuid4().hex[:12]}"
    body = NoteCreate(figure_slug="ada-lovelace", body="Same key, different owner")
    mine, created = await store.create_note(TEST_OWNER, body, key)
    theirs, created_theirs = await store.create_note(f"{TEST_OWNER}-2", body, key)
    assert created and created_theirs and mine.id != theirs.id


@needs_db
async def test_create_collection_when_key_reused_for_other_request_then_conflict(store: Store) -> None:
    key = f"test-{uuid.uuid4().hex[:12]}"
    await store.create_collection(TEST_OWNER, CollectionCreate(name=f"c-{key}"), key)
    with pytest.raises(IdempotencyConflict):
        await store.create_collection(TEST_OWNER, CollectionCreate(name=f"other-{key}"), key)
