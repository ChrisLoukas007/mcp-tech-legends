"""Tool outputs. Defined here, not imported from the API package: the MCP server and the private
app are separate systems that only share an HTTP contract."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


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
