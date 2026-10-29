"""Outbound HTTP to public APIs, done safely. No MCP imports.

Every request goes through `_get_json`, which enforces the rules for calling the internet:
    https only, host on an allow-list (blocks SSRF), no redirects, timeout, response size cap,
    limited concurrency, and a TTL cache so repeated questions do not hammer Wikimedia.

Errors: LookupError (page does not exist), UpstreamUnavailable (network, timeout, 5xx, too big),
PermissionError (blocked host). tools.py turns them into messages the model can act on.
"""

from __future__ import annotations

import asyncio
import html
import json
import re
import time
from typing import Any
from urllib.parse import quote, urlsplit

import httpx2

from wiki_mcp.config import Settings
from wiki_mcp.models import SearchHit, SearchResults, Summary, WikidataFacts

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
WIKIDATA_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"

MAX_EXTRACT_CHARS = 2_000
MAX_LIST_ITEMS = 5
PROPERTIES = {"citizenship": "P27", "employers": "P108", "notable_works": "P800", "awards": "P166"}


class UpstreamUnavailable(Exception):
    """The public API could not be reached or answered badly."""


class WikiBackend:
    def __init__(self, settings: Settings, transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        self._transport = transport
        self._client: httpx2.AsyncClient | None = None
        self._limit = asyncio.Semaphore(settings.max_concurrent_requests)
        self._cache: dict[str, tuple[float, Any]] = {}

    async def start(self) -> None:
        self._client = httpx2.AsyncClient(
            headers={"User-Agent": self._settings.user_agent, "Accept": "application/json"},
            timeout=self._settings.timeout_seconds,
            follow_redirects=False,
            transport=self._transport,
        )

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def ready(self) -> bool:
        return self._client is not None  # do not ping Wikipedia on every probe

    async def search(self, query: str, limit: int) -> SearchResults:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": str(limit),
            "format": "json",
        }
        data = await self._get_json(WIKIPEDIA_API, params)
        hits = [
            SearchHit(title=h["title"], snippet=_strip_html(h.get("snippet", "")))
            for h in data.get("query", {}).get("search", [])
        ]
        return SearchResults(query=query, hits=hits)

    async def summary(self, title: str) -> Summary:
        data = await self._get_json(WIKIPEDIA_SUMMARY + quote(title.strip().replace(" ", "_"), safe=""))
        return Summary(
            title=data["title"],
            description=data.get("description"),
            extract=data.get("extract", "")[:MAX_EXTRACT_CHARS],
            url=data.get("content_urls", {}).get("desktop", {}).get("page", ""),
            wikidata_id=data.get("wikibase_item"),
        )

    async def wikidata_facts(self, entity_id: str) -> WikidataFacts:
        data = await self._get_json(f"{WIKIDATA_ENTITY}{entity_id}.json")
        entity = data["entities"][entity_id]
        claims = entity.get("claims", {})
        item_ids = {key: _item_ids(claims, prop)[:MAX_LIST_ITEMS] for key, prop in PROPERTIES.items()}
        labels = await self._labels([i for ids in item_ids.values() for i in ids])
        return WikidataFacts(
            id=entity_id,
            label=entity.get("labels", {}).get("en", {}).get("value", entity_id),
            description=entity.get("descriptions", {}).get("en", {}).get("value"),
            born=_date(claims, "P569"),
            died=_date(claims, "P570"),
            url=f"https://www.wikidata.org/wiki/{entity_id}",
            citizenship=[labels.get(i, i) for i in item_ids["citizenship"]],
            employers=[labels.get(i, i) for i in item_ids["employers"]],
            notable_works=[labels.get(i, i) for i in item_ids["notable_works"]],
            awards=[labels.get(i, i) for i in item_ids["awards"]],
        )

    async def _labels(self, ids: list[str]) -> dict[str, str]:
        if not ids:
            return {}
        params = {"action": "wbgetentities", "ids": "|".join(sorted(set(ids))), "props": "labels",
                  "languages": "en", "format": "json"}  # fmt: skip
        data = await self._get_json(WIKIDATA_API, params)
        return {
            qid: e.get("labels", {}).get("en", {}).get("value", qid)
            for qid, e in data.get("entities", {}).items()
        }

    async def _get_json(self, url: str, params: dict[str, str] | None = None) -> Any:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in self._settings.allowed_upstream_hosts:
            raise PermissionError(f"blocked outbound request to {parts.hostname!r}")
        key = url + "?" + json.dumps(params or {}, sort_keys=True)
        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < self._settings.cache_ttl_seconds:
            return cached[1]
        data = json.loads(await self._fetch(url, params))
        self._cache[key] = (time.monotonic(), data)
        return data

    async def _fetch(self, url: str, params: dict[str, str] | None) -> bytes:
        if self._client is None:
            raise RuntimeError("http client not started")
        async with self._limit:
            try:
                async with self._client.stream("GET", url, params=params) as response:
                    if response.status_code == 404:
                        raise LookupError(url)
                    if response.status_code >= 300:
                        raise UpstreamUnavailable(f"HTTP {response.status_code}")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body += chunk
                        if len(body) > self._settings.max_response_bytes:
                            raise UpstreamUnavailable("response too large")
                    return bytes(body)
            except httpx2.HTTPError as exc:
                raise UpstreamUnavailable(type(exc).__name__) from exc


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text))


def _item_ids(claims: dict[str, Any], prop: str) -> list[str]:
    values = (c.get("mainsnak", {}).get("datavalue", {}).get("value") for c in claims.get(prop, []))
    return [v["id"] for v in values if isinstance(v, dict) and "id" in v]


def _date(claims: dict[str, Any], prop: str) -> str | None:
    for claim in claims.get(prop, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and "time" in value:
            return str(value["time"]).lstrip("+").split("T")[0]
    return None
