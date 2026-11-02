"""Step 3 of 7, audit: HOW every call is recorded, allowed or denied.

Logs are for debugging and may be sampled or rotated away; the audit trail answers "who did
what, when, and was it allowed?" and is never edited. One record per tool call or resource read.

Arguments are stored only as a SHA-256 fingerprint, so the audit store never becomes a
second copy of personal data: you can prove two calls had the same arguments without storing
them. A sink is a place records are written to:

    LogAuditSink       always on: a JSON log line with event="audit"
    PostgresAuditSink  when AUDIT_DATABASE_URL is set: INSERT into audit.events through a
                       role that can INSERT but not UPDATE or DELETE (infra/postgres/02_roles.sql)
    FanOutAuditSink    writes each record to several sinks

A failed audit write never fails the business call; it increments a metric that alerts.

Next: policy.py (the gate that produces these records).
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Protocol

import asyncpg

from mcp_kit.observability import AUDIT_WRITE_FAILURES

logger = logging.getLogger("audit")

MAX_ERROR_LENGTH = 500


def fingerprint(payload: Mapping[str, Any]) -> str:
    """Stable SHA-256 of a request: same arguments, same hash, regardless of key order."""
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class AuditEvent:
    server: str
    correlation_id: str
    subject: str
    client_id: str
    operation: str
    args_sha256: str
    outcome: str
    duration_ms: int
    error: str | None = None


class AuditSink(Protocol):
    async def record(self, event: AuditEvent) -> None: ...


class LogAuditSink:
    async def record(self, event: AuditEvent) -> None:
        logger.info("audit", extra={"event": "audit", **asdict(event)})


class PostgresAuditSink:
    """Opens its own small pool on first use, so servers without a database still audit."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def record(self, event: AuditEvent) -> None:
        try:
            if self._pool is None:
                self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=2)
            await self._pool.execute(
                """
                INSERT INTO audit.events (server, correlation_id, subject, client_id, operation,
                                          args_sha256, outcome, duration_ms, error)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                event.server,
                event.correlation_id,
                event.subject,
                event.client_id,
                event.operation,
                event.args_sha256,
                event.outcome,
                event.duration_ms,
                event.error[:MAX_ERROR_LENGTH] if event.error else None,
            )
        except (asyncpg.PostgresError, OSError, TimeoutError):
            AUDIT_WRITE_FAILURES.labels(server=event.server).inc()
            logger.exception("audit write failed", extra={"correlation_id": event.correlation_id})


class FanOutAuditSink:
    def __init__(self, *sinks: AuditSink) -> None:
        self._sinks = sinks

    async def record(self, event: AuditEvent) -> None:
        for sink in self._sinks:
            await sink.record(event)
