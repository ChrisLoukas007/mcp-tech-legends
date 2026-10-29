# 5. Observability

Previous: [4. Security](04-security.md). Back to the [README](../README.md).

Three signals, each answering a different question.

| Signal | Answers | Where it goes | Look at |
|---|---|---|---|
| **Logs** | what happened in this process | JSON on stderr (`docker compose logs`) | `mcp_kit/observability.py` |
| **Metrics** | how much, how fast, how often it fails | Prometheus, scraped every 15 s | http://localhost:9091 |
| **Traces** | where did this one request go and how long each hop took | Tempo, via OTLP | Grafana > Explore > Tempo |
| **Audit** | who did what, with which outcome (for investigations) | `audit.events` + `event=audit` log lines | `mcp_kit/audit.py` |

```
 agent-cli ──spans──┐
 figures-db-mcp ────┤                      ┌── metrics ◀── Prometheus :9091 ──┐
 hall-of-fame-mcp ──┼──OTLP :4318──▶ Tempo :3200                            ├──▶ Grafana :3001
 wiki-mcp ──────────┘                      └── traces ─────────────────────┘
```

## Logs

One JSON object per line, on **stderr** (stdout belongs to the stdio transport). Inside a
request, each line carries the `trace_id`, so you can jump from a log line to its trace.
Tokens and arguments are never logged; audit lines carry a SHA-256 of the arguments.

Known gap: uvicorn's own access log lines (`GET /metrics ... 200`) are plain text, because the
SDK starts uvicorn with its own logging config.

## Metrics

Defined once in `mcp_kit/observability.py`, labelled by `server`, so one dashboard covers all:

| Metric | Type | Labels |
|---|---|---|
| `mcp_tool_calls_total` | counter | server, operation, outcome (ok, denied, error, crash) |
| `mcp_tool_duration_seconds` | histogram | server, operation |
| `mcp_authz_denied_total` | counter | server, operation, scope |
| `mcp_audit_write_failures_total` | counter | server |

Dashboard "MCP servers" (Grafana, folder Tech Legends): calls per second, outcomes, p95
latency, denials, audit failures, servers up. Alert rules (`infra/prometheus/alert-rules.yml`):
server down, a spike of permission denials (possible prompt injection), audit writes failing.

## Traces: one question, one trace

You get this for free from the MCP SDK: the client puts W3C `traceparent` into each request's
`_meta`, and the server continues the trace. `mcp_kit` only installs an exporter
(`configure_tracing`). `hall-of-fame-mcp` also injects `traceparent` into its REST calls.

```
 agent.turn                                   agent-cli
 ├── MCP send tools/call compare_figures      agent-cli
 │   └── tools/call compare_figures           figures-db-mcp
 ├── MCP send tools/call get_wikipedia_summary
 │   └── tools/call get_wikipedia_summary     wiki-mcp
 └── MCP send tools/call list_collections
     └── tools/call list_collections          hall-of-fame-mcp
```

Try it: `make up`, then `make demo` (needs `ANTHROPIC_API_KEY`), then Grafana > Explore >
Tempo > Search, service `agent-cli`. Stdio servers launched from `.mcp.json` do not export
traces unless you add `<PREFIX>_OTLP_ENDPOINT=http://localhost:4318` to their env.

## When something is wrong

| Symptom | First place to look |
|---|---|
| Model says "permission denied" | Grafana denials panel; `audit.events` where outcome = 'denied' |
| Slow answers | p95 panel, then the trace: which hop is long? |
| "operation failed (reference abc...)" | `docker compose logs <server> | grep abc...` |
| Prometheus target down | `docker compose ps`; the server's `/readyz` |
