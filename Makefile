COMPOSE ?= docker compose

.PHONY: up down migrate seed codegen test eval bootstrap

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
