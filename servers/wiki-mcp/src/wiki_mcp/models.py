"""Tool outputs. Every result says where it came from and that its text is untrusted web content."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Trust = Literal["untrusted-web-content"]


class SearchHit(BaseModel):
    title: str
    snippet: str


class SearchResults(BaseModel):
    query: str
    hits: list[SearchHit]
    source: str = "en.wikipedia.org"
    trust: Trust = "untrusted-web-content"


class Summary(BaseModel):
    title: str
    description: str | None
    extract: str
    url: str
    wikidata_id: str | None
    source: str = "en.wikipedia.org"
    trust: Trust = "untrusted-web-content"


class WikidataFacts(BaseModel):
    id: str
    label: str
    description: str | None
    born: str | None
    died: str | None
    citizenship: list[str]
    employers: list[str]
    notable_works: list[str]
    awards: list[str]
    url: str
    source: str = "www.wikidata.org"
    trust: Trust = "untrusted-web-content"
