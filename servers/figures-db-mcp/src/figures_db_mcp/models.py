"""What the tools return. Pydantic models become the tools' output schema (structuredContent)."""

from __future__ import annotations

from pydantic import BaseModel


class FigureSummary(BaseModel):
    slug: str
    name: str
    born: int
    died: int | None
    known_for: str


class Affiliation(BaseModel):
    organization: str
    role: str
    from_year: int


class FigureProfile(FigureSummary):
    country: str
    bio: str
    affiliations: list[Affiliation]


class Product(BaseModel):
    slug: str
    name: str
    year: int
    category: str
    organization: str | None
    lead_figure: str | None
    description: str


class Milestone(BaseModel):
    year: int
    title: str


class Comparison(BaseModel):
    slug: str
    name: str
    born: int
    first_product: str | None
    first_product_year: int | None
    product_count: int
    organizations: list[str]


class Organization(BaseModel):
    slug: str
    name: str
    kind: str
    founded: int
    location: str
