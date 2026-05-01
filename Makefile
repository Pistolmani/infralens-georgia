COMPOSE ?= docker compose
API_BASE_URL ?= http://localhost:8000
SMOKE_REPORT ?= Streetlights are out on Rustaveli Avenue near the bus stop.
SMOKE_LANGUAGE_HINT ?= en
SMOKE_LOCATION_HINT ?= Rustaveli Avenue
SMOKE_TIMEOUT_SECONDS ?= 180
SMOKE_POLL_SECONDS ?= 2

.PHONY: up down migrate seed codegen test eval bootstrap smoke-analysis

up:
	$(COMPOSE) up --build

down:
	$(COMPOSE) down

migrate:
	$(COMPOSE) run --rm api alembic upgrade head

seed:
	@echo "Seed ingestion is not implemented in Milestone 1."

codegen:
	$(COMPOSE) run --rm -e OPENAPI_URL=http://api:8000/openapi.json web npm run codegen

test:
	@if [ -x .venv/bin/python ]; then \
		.venv/bin/python -m pytest apps/api/tests; \
	else \
		$(COMPOSE) run --rm --no-deps api pytest; \
	fi

eval:
	@echo "Eval execution is not implemented in Milestone 1."

bootstrap:
	./scripts/bootstrap-ollama.sh

smoke-analysis:
	@if [ -x .venv/bin/python ]; then \
		API_BASE_URL="$(API_BASE_URL)" \
		SMOKE_REPORT="$(SMOKE_REPORT)" \
		SMOKE_LANGUAGE_HINT="$(SMOKE_LANGUAGE_HINT)" \
		SMOKE_LOCATION_HINT="$(SMOKE_LOCATION_HINT)" \
		SMOKE_TIMEOUT_SECONDS="$(SMOKE_TIMEOUT_SECONDS)" \
		SMOKE_POLL_SECONDS="$(SMOKE_POLL_SECONDS)" \
		.venv/bin/python scripts/smoke-analysis.py; \
	else \
		API_BASE_URL="$(API_BASE_URL)" \
		SMOKE_REPORT="$(SMOKE_REPORT)" \
		SMOKE_LANGUAGE_HINT="$(SMOKE_LANGUAGE_HINT)" \
		SMOKE_LOCATION_HINT="$(SMOKE_LOCATION_HINT)" \
		SMOKE_TIMEOUT_SECONDS="$(SMOKE_TIMEOUT_SECONDS)" \
		SMOKE_POLL_SECONDS="$(SMOKE_POLL_SECONDS)" \
		python3 scripts/smoke-analysis.py; \
	fi
