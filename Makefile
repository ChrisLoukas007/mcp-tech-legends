# Everyday commands. Run `make help` for the list.
#
# A Makefile is a menu of named shortcuts: `make up` runs the commands listed under `up:`.
# Nothing here is needed to understand the code; it only saves you typing long commands.
#
# A typical first session:
#   make env      create .env with random local passwords (once)
#   make up       build the image and start all 9 containers, wait until healthy
#   make test     fast unit tests, no Docker
#   make test-integration   every test, against the running stack
#   make demo     ask the custom host one real question (needs ANTHROPIC_API_KEY)
#   make down     stop everything, keep the data
#
# Each target's text after `##` is what `make help` prints, so keep it on the same line.

# One name for the long compose command. The compose file lives in infra/, but .env lives at
# the repo root, so --env-file is required; without it every ${VAR:?} in the compose file fails.
COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env

# Read .env as Make variables (the leading "-" means: no error if .env does not exist yet),
# then `export` passes every one of them to the commands below as environment variables.
# That is how test-integration can build database URLs from the passwords in .env.
-include .env
export

# Prints every line of this file that looks like `name:  ## text`, as a two-column list.
help:  ## list targets
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-18s %s\n", $$1, $$2}'

# Copies .env.example line by line: blank lines and # comments are kept, and every KEY= gets a
# fresh random 32-character hex value. Does nothing if .env already exists, so it never
# overwrites passwords that your database volume was created with. ($$ is how Make writes $.)
env:  ## create .env with random local passwords (once)
	@test -f .env || { while IFS='=' read -r k v; do case "$$k" in ''|\#*) echo "$$k";; *) echo "$$k=$$(openssl rand -hex 16)";; esac; done < .env.example > .env; echo "wrote .env"; }

# --build  rebuild the tech-legends:local image if the code changed
# -d       run in the background and give the terminal back
# --wait   return only when every container with a healthcheck reports healthy
up:  ## start the stack and wait until healthy
	$(COMPOSE) up -d --build --wait

# Removes the containers. Named volumes (pgdata, tempodata) stay, so data survives.
down:  ## stop the stack (keeps data)
	$(COMPOSE) down

# -v also deletes the named volumes: all notes, audit rows and traces are gone. The next
# `make up` starts with an empty database, so Postgres runs 01_schema, 02_roles and 03_seed
# again. Use it after changing any file in infra/postgres/.
reset:  ## stop the stack and delete all data (re-seeds on next up)
	$(COMPOSE) down -v

# Rewrites 03_seed.sql from the data in generate_seed.py. Does not touch a running database.
seed:  ## regenerate infra/postgres/03_seed.sql (then `make reset up` to load it)
	uv run python infra/postgres/generate_seed.py

# Checks only, changes nothing: formatting, lint rules and types (settings in pyproject.toml).
# To fix formatting: uv run ruff format .
lint:  ## ruff + mypy
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy

# Skips every test marked `integration`, so it runs in seconds without Docker. It does NOT run
# the security tests against real Keycloak and Postgres; test-integration does.
test:  ## unit tests (no Docker needed)
	uv run pytest -q -m "not integration"

# Runs ALL tests, including the integration ones, against the stack started by `make up`.
# Tests run on your machine, so URLs use localhost:5433 (the host port), not postgres:5432.
# Each URL uses the role that the real service uses, so the tests prove its permissions.
# The leading @ hides the command, because it contains the passwords from .env.
test-integration:  ## all tests against the running stack
	@FIGURES_DB_MCP_DATABASE_URL=postgresql://figures_reader:$(FIGURES_READER_PASSWORD)@localhost:5433/legends \
	HALL_OF_FAME_API_DATABASE_URL=postgresql://halloffame_app:$(HALLOFFAME_APP_PASSWORD)@localhost:5433/legends \
	POSTGRES_ADMIN_URL=postgresql://postgres:$(POSTGRES_PASSWORD)@localhost:5433/legends \
	AGENT_CLI_E2E=1 uv run pytest -q

# The full system in one command: logs in as ada over HTTP (one token per server), asks a
# question that needs all three servers, and sends its trace spans to Tempo so you can find
# it in Grafana (Explore -> Tempo). Needs `make up` first.
demo:  ## ask the custom host one question over HTTP as ada (needs ANTHROPIC_API_KEY)
	AGENT_CLI_OTLP_ENDPOINT=http://localhost:4318 uv run agent-cli --transport http --user ada \
	  --ask "Compare Steve Jobs and Bill Gates' first products, check Wikipedia for anything missing, and save a short note about Bill Gates to my Hall of Fame."

# Interactive chat. Uses stdio: agent-cli starts the three servers itself from .mcp.json, with
# no Keycloak and no tokens. Needs Postgres running (make up) for figures and audit.
chat:  ## chat with the custom host, servers over stdio (needs ANTHROPIC_API_KEY)
	uv run agent-cli

# These names are commands, not files: run them even if a file with the same name exists.
.PHONY: help env up down reset seed lint test test-integration demo chat
