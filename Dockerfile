# A Dockerfile is a recipe for an image: a frozen, self-contained filesystem with Python,
# our code and its dependencies, so the app runs the same on any machine.
#
# How this repo uses it:
# - One image for every Python service (servers, apps, hosts). docker-compose starts each
#   container from this image and only changes the command it runs.
# - Two stages, like a kitchen and a plate: "builder" has the tools to install everything,
#   "runtime" receives only the finished result. The final image is smaller and has no
#   build tools (uv, compilers) an attacker could use.
# - It runs as a non-root user, so a compromised service cannot take over the container.

# Stage 0: borrow the pinned uv binary from its official image.
FROM ghcr.io/astral-sh/uv:0.13.5 AS uv

# Stage 1 (builder): install all workspace packages into /app/.venv.
FROM python:3.12-slim AS builder
COPY --from=uv /uv /usr/local/bin/uv
# Precompile .pyc for faster startup, copy files instead of hardlinking (the venv must be
# self-contained to move to the next stage), and use the image's Python, never a download.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY packages ./packages
COPY servers ./servers
COPY apps ./apps
COPY hosts ./hosts
# --frozen: install exactly what uv.lock says, fail if it is out of date.
# --no-dev: skip test and lint tools.
# --no-editable: copy our code into the venv, so the venv alone is enough to run it.
RUN uv sync --frozen --no-dev --no-editable

# Stage 2 (runtime): a clean Python image plus the finished venv, nothing else.
FROM python:3.12-slim AS runtime
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --no-create-home app
WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
# Put the venv first on PATH so "python" and console scripts come from it; unbuffered
# output so logs appear in "docker compose logs" immediately.
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER 10001:10001
