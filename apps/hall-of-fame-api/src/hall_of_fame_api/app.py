"""The private REST API. Every route needs a verified Caller and only ever sees that user's data.

GET  /collections                       list my collections
GET  /collections/{id}                  one collection with its figures (404 if not mine)
POST /collections        Idempotency-Key  create a collection
PUT  /collections/{id}/items/{slug}     add a figure (naturally idempotent)
GET  /notes?figure_slug=                my notes
POST /notes              Idempotency-Key  create a note
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any

import asyncpg
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from hall_of_fame_api.auth import Caller, CallerVerifier, jwks_resolver
from hall_of_fame_api.config import Settings
from hall_of_fame_api.models import (
    Collection,
    CollectionCreate,
    CollectionDetail,
    FigureSlug,
    Note,
    NoteCreate,
)
from hall_of_fame_api.store import IdempotencyConflict, Store

IdempotencyKey = Annotated[str, Header(pattern=r"^[A-Za-z0-9_-]{8,64}$")]


def _rate_key(request: Request) -> str:
    return request.headers.get("x-acting-user") or (request.client.host if request.client else "unknown")


def get_store(request: Request) -> Store:
    store: Store = request.app.state.store
    return store


def get_caller(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_acting_user: Annotated[str | None, Header()] = None,
) -> Caller:
    verifier: CallerVerifier = request.app.state.verifier
    return verifier.verify(authorization, x_acting_user)


# Module level on purpose: with `from __future__ import annotations` FastAPI resolves these by name.
CallerDep = Annotated[Caller, Depends(get_caller)]
StoreDep = Annotated[Store, Depends(get_store)]


def create_app(settings: Settings, key_resolver: Callable[[str], Any] | None = None) -> FastAPI:
    verifier = CallerVerifier(
        issuer=settings.issuer_url,
        audience=settings.audience,
        trusted_callers=settings.trusted_callers,
        key_resolver=key_resolver or jwks_resolver(settings.jwks_url),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pool = await asyncpg.create_pool(settings.database_url.get_secret_value(), min_size=1, max_size=5)
        app.state.store = Store(pool)
        yield
        await pool.close()

    limiter = Limiter(key_func=_rate_key, default_limits=[settings.rate_limit])
    app = FastAPI(title="Hall of Fame API (private)", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.limiter = limiter
    app.state.verifier = verifier
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_api_route("/healthz", lambda: {"status": "alive"}, methods=["GET"])
    _add_routes(app)
    return app


def _add_routes(app: FastAPI) -> None:
    @app.get("/collections", response_model=list[Collection])
    async def list_collections(caller: CallerDep, store: StoreDep) -> list[Collection]:
        return await store.list_collections(caller.user)

    @app.get("/collections/{collection_id}", response_model=CollectionDetail)
    async def get_collection(collection_id: int, caller: CallerDep, store: StoreDep) -> CollectionDetail:
        found = await store.get_collection(caller.user, collection_id)
        if found is None:  # same answer for "missing" and "someone else's": no existence leak
            raise HTTPException(status.HTTP_404_NOT_FOUND, "collection not found")
        return found

    @app.post("/collections", response_model=Collection, status_code=status.HTTP_201_CREATED)
    async def create_collection(body: CollectionCreate, idempotency_key: IdempotencyKey, caller: CallerDep,
                                store: StoreDep, response: Response) -> Collection:  # fmt: skip
        try:
            collection, created = await store.create_collection(caller.user, body, idempotency_key)
        except IdempotencyConflict:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Idempotency-Key reused for a different request"
            ) from None
        except asyncpg.UniqueViolationError:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "you already have a collection with that name"
            ) from None
        if not created:
            response.status_code = status.HTTP_200_OK
        return collection

    @app.put("/collections/{collection_id}/items/{figure_slug}", response_model=CollectionDetail)
    async def add_item(collection_id: int, figure_slug: FigureSlug, caller: CallerDep,
                       store: StoreDep) -> CollectionDetail:  # fmt: skip
        found = await store.add_item(caller.user, collection_id, figure_slug)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "collection not found")
        return found

    @app.get("/notes", response_model=list[Note])
    async def list_notes(
        caller: CallerDep, store: StoreDep, figure_slug: FigureSlug | None = None
    ) -> list[Note]:
        return await store.list_notes(caller.user, figure_slug)

    @app.post("/notes", response_model=Note, status_code=status.HTTP_201_CREATED)
    async def create_note(body: NoteCreate, idempotency_key: IdempotencyKey, caller: CallerDep,
                          store: StoreDep, response: Response) -> Note:  # fmt: skip
        try:
            note, created = await store.create_note(caller.user, body, idempotency_key)
        except IdempotencyConflict:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Idempotency-Key reused for a different request"
            ) from None
        if not created:
            response.status_code = status.HTTP_200_OK
        return note
