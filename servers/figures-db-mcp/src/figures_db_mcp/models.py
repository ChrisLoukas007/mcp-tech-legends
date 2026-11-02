"""Step 2 of 6, models: WHAT each answer looks like.

Only shapes, no logic. backend.py fills these models; tools.py returns them. The MCP SDK turns
each return type into the tool's output schema, so the model knows the fields before it calls the
tool, and the result is sent back as structured JSON (structuredContent), not just text.

Next: backend.py (how the data is fetched).
"""

from __future__ import annotations

from pydantic import BaseModel


# Returned by search_figures (short) and extended by FigureProfile below.
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


# Returned by get_figure: the summary fields plus bio and affiliations.
class FigureProfile(FigureSummary):
    country: str
    bio: str
    affiliations: list[Affiliation]


# Returned by list_products.
class Product(BaseModel):
    slug: str
    name: str
    year: int
    category: str
    organization: str | None
    lead_figure: str | None
    description: str


# Returned by get_timeline.
class Milestone(BaseModel):
    year: int
    title: str


# One row of compare_figures.
class Comparison(BaseModel):
    slug: str
    name: str
    born: int
    first_product: str | None
    first_product_year: int | None
    product_count: int
    organizations: list[str]


# Returned by the legends://organizations resource (server.py).
class Organization(BaseModel):
    slug: str
    name: str
    kind: str
    founded: int
    location: str
