"""One way to build and run every server in this repo.

A server provides three things and `serve()` does the rest:

    ServerInfo   name, title, version, instructions for the model
    Backend      the thing it wraps (DB pool, REST client, web client): start/stop/ready
    register()   adds its tools, resources and prompts, capturing backend + policy

`serve()` then wires logging, tracing, audit, auth (http) or a local identity (stdio),
health probes and /metrics, and runs the chosen transport.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol

from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mcp_kit.audit import AuditSink, FanOutAuditSink, LogAuditSink, PostgresAuditSink
from mcp_kit.auth import JwtTokenVerifier, jwks_resolver
from mcp_kit.observability import configure_logging, configure_tracing
from mcp_kit.policy import Policy, set_stdio_principal
from mcp_kit.settings import ServerSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ServerInfo:
    name: str  # also the metrics label and the audit "server" field
    title: str
    version: str
    instructions: str


class Backend(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def ready(self) -> bool: ...


type Register[B: Backend] = Callable[[MCPServer[Any], B, Policy], None]


def build_policy(info: ServerInfo, settings: ServerSettings) -> Policy:
    sinks: list[AuditSink] = [LogAuditSink()]
    if settings.audit_database_url is not None:
        sinks.append(PostgresAuditSink(settings.audit_database_url.get_secret_value()))
    return Policy(server=info.name, audit=FanOutAuditSink(*sinks))


def create_server[B: Backend](
    info: ServerInfo,
    settings: ServerSettings,
    backend: B,
    register: Register[B],
    *,
    with_auth: bool,
) -> MCPServer[Any]:
    @asynccontextmanager
    async def lifespan(_: MCPServer[Any]) -> AsyncIterator[B]:
        await backend.start()
        try:
            yield backend
        finally:
            await backend.stop()

    verifier, auth = _oauth(settings) if with_auth else (None, None)
    server: MCPServer[Any] = MCPServer(
        info.name,
        title=info.title,
        version=info.version,
        instructions=info.instructions,
        lifespan=lifespan,
        log_level=settings.log_level,
        token_verifier=verifier,
        auth=auth,
    )
    register(server, backend, build_policy(info, settings))
    _register_http_endpoints(server, backend)
    return server


def serve[B: Backend](info: ServerInfo, settings: ServerSettings, backend: B, register: Register[B]) -> None:
    configure_logging(settings.log_level)
    configure_tracing(info.name, settings.otlp_endpoint)
    if settings.transport == "stdio":
        if not settings.stdio_scopes:
            raise SystemExit(f"{info.name}: stdio mode needs <PREFIX>_STDIO_SCOPES, e.g. '[\"wiki:read\"]'.")
        set_stdio_principal(settings.stdio_subject, settings.stdio_scopes, settings.stdio_roles)
        create_server(info, settings, backend, register, with_auth=False).run("stdio")
        return
    server = create_server(info, settings, backend, register, with_auth=True)
    logger.info("starting streamable-http", extra={"server": info.name, "port": settings.port})
    server.run(
        "streamable-http",
        host=settings.host,
        port=settings.port,
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(allowed_hosts=settings.allowed_hosts),
    )


def _oauth(settings: ServerSettings) -> tuple[JwtTokenVerifier, AuthSettings]:
    verifier = JwtTokenVerifier(
        issuer=settings.issuer_url,
        audience=settings.audience,
        key_resolver=jwks_resolver(settings.resolved_jwks_url),
    )
    auth = AuthSettings(
        issuer_url=AnyHttpUrl(settings.issuer_url),
        resource_server_url=AnyHttpUrl(settings.public_url),
        validate_token_resource=False,  # the verifier already checks `aud`
    )
    return verifier, auth


def _register_http_endpoints(server: MCPServer[Any], backend: Backend) -> None:
    """Plain HTTP routes outside MCP. The SDK serves them without bearer auth, which is right
    for probes; in production keep /metrics on the internal network only."""

    @server.custom_route("/healthz", methods=["GET"], include_in_schema=False)  # type: ignore[untyped-decorator]
    async def liveness(_: Request) -> Response:
        return JSONResponse({"status": "alive"})

    @server.custom_route("/readyz", methods=["GET"], include_in_schema=False)  # type: ignore[untyped-decorator]
    async def readiness(_: Request) -> Response:
        ready = await backend.ready()
        return JSONResponse({"status": "ready" if ready else "not ready"}, status_code=200 if ready else 503)

    @server.custom_route("/metrics", methods=["GET"], include_in_schema=False)  # type: ignore[untyped-decorator]
    async def metrics(_: Request) -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
