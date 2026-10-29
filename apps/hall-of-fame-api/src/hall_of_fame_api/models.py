"""Request and response bodies. Requests forbid unknown fields; responses are explicit models."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

FigureSlug = Annotated[str, Field(pattern=r"^[a-z0-9-]{2,60}$")]


class CollectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, Field(min_length=2, max_length=80)]
    description: Annotated[str, Field(max_length=500)] = ""


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    figure_slug: FigureSlug
    body: Annotated[str, Field(min_length=3, max_length=2000)]


class Collection(BaseModel):
    id: int
    name: str
    description: str
    created_at: datetime


class CollectionDetail(Collection):
    figure_slugs: list[str]


class Note(BaseModel):
    id: int
    figure_slug: str
    body: str
    created_at: datetime
