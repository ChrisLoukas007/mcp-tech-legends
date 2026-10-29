"""The three signals every server emits.

logs     JSON lines on stderr (stdout belongs to the stdio transport), with trace_id
metrics  Prometheus counters/histograms, labelled by server and tool
traces   OpenTelemetry spans exported over OTLP. The MCP SDK already creates a span per
         request and carries `traceparent` in `_meta`, so host and server spans join up.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram

_STANDARD_ATTRS = frozenset(vars(logging.makeLogRecord({})))

# --- metrics -------------------------------------------------------------------------

TOOL_CALLS = Counter(
    "mcp_tool_calls_total",
    "Tool calls and resource reads, by server, operation and outcome (ok, denied, error, crash).",
    ["server", "operation", "outcome"],
)
TOOL_DURATION = Histogram(
    "mcp_tool_duration_seconds",
    "Wall-clock duration of tool calls and resource reads.",
    ["server", "operation"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
AUTHZ_DENIED = Counter(
    "mcp_authz_denied_total",
    "Calls rejected because the caller lacked a scope or role.",
    ["server", "operation", "scope"],
)
AUDIT_WRITE_FAILURES = Counter(
    "mcp_audit_write_failures_total",
    "Audit rows that could not be written. Any increase should page someone.",
    ["server"],
)

# --- logs ----------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            payload["trace_id"] = format(span_context.trace_id, "032x")
        payload.update({k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRS})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


# --- traces --------------------------------------------------------------------------


def configure_tracing(service_name: str, otlp_endpoint: str | None) -> None:
    """Install an exporter. Without an endpoint, spans are created but dropped (no-op)."""
    if not otlp_endpoint:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")))
    trace.set_tracer_provider(provider)
