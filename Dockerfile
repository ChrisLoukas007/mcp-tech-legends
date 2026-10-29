# One image for every Python service in the workspace; docker-compose picks the command.
# Multi-stage: uv resolves dependencies in the builder; the runtime image has only the
# virtualenv and source, runs as a non-root user, and has no compiler or uv binary.

FROM ghcr.io/astral-sh/uv:0.13.5 AS uv

FROM python:3.12-slim AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY packages ./packages
COPY servers ./servers
COPY apps ./apps
COPY hosts ./hosts
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim AS runtime
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --no-create-home app
WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER 10001:10001
