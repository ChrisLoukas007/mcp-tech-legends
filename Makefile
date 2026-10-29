# Everyday commands. Run `make help` for the list.
COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env
-include .env
export

help:  ## list targets
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-18s %s\n", $$1, $$2}'

env:  ## create .env with random local passwords (once)
	@test -f .env || { while IFS='=' read -r k v; do case "$$k" in ''|\#*) echo "$$k";; *) echo "$$k=$$(openssl rand -hex 16)";; esac; done < .env.example > .env; echo "wrote .env"; }

up:  ## start the stack and wait until healthy
	$(COMPOSE) up -d --build --wait

down:  ## stop the stack (keeps data)
	$(COMPOSE) down

reset:  ## stop the stack and delete all data (re-seeds on next up)
	$(COMPOSE) down -v

seed:  ## regenerate infra/postgres/03_seed.sql (then `make reset up` to load it)
	uv run python infra/postgres/generate_seed.py

lint:  ## ruff + mypy
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy

test:  ## unit tests (no Docker needed)
	uv run pytest -q -m "not integration"

test-integration:  ## all tests against the running stack
	@FIGURES_DB_MCP_DATABASE_URL=postgresql://figures_reader:$(FIGURES_READER_PASSWORD)@localhost:5433/legends \
	HALL_OF_FAME_API_DATABASE_URL=postgresql://halloffame_app:$(HALLOFFAME_APP_PASSWORD)@localhost:5433/legends \
	POSTGRES_ADMIN_URL=postgresql://postgres:$(POSTGRES_PASSWORD)@localhost:5433/legends \
	AGENT_CLI_E2E=1 uv run pytest -q

.PHONY: help env up down reset seed lint test test-integration
