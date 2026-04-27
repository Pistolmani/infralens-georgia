# InfraLens Georgia

InfraLens Georgia is a local-first portfolio app for Georgian municipal infrastructure incident analysis. Milestone 1 creates the runnable foundation only: FastAPI, Next.js, PostgreSQL with pgvector, Redis/RQ, Ollama wiring, Alembic migrations, and scaffold tests.

## Requirements

- Docker Desktop or a Docker Engine with Compose v2
- Enough local memory to run PostgreSQL, Redis, the web/API containers, and Ollama models
- Ollama models are local only; v1 does not use hosted LLM APIs

`qwen3:8b` can be memory-heavy. If model pulls or analysis fail later, check local RAM/VRAM before changing the app design.

## Startup

1. Copy `.env.example` to `.env` if you want to override defaults.
2. Start services with `make up` and leave that terminal running.
3. In another terminal, apply migrations with `make migrate`.
4. Pull local models with `make bootstrap` after Ollama is running.
5. Run scaffold tests with `make test`.

Default local URLs:

- Web: http://localhost:3000
- API: http://localhost:8000
- Health: http://localhost:8000/healthz
- Ollama: http://localhost:11434

## Milestone 1 Boundaries

This scaffold intentionally does not implement procurement ingestion, RAG retrieval, LangGraph analysis, eval execution, or the complete incident workflow. Those features should be added in later milestones using the module boundaries documented in `docs/architecture.md`.
