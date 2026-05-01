# InfraLens Georgia

InfraLens Georgia is a local-first civic infrastructure analysis project focused on Georgian municipal incident reports. It is designed to turn Georgian or English free-text reports into structured incident records with issue classification, extracted entities, supporting procurement evidence, bilingual Georgian/English briefs, citation grounding, and traceable local-model execution.

The current implementation ships the runnable foundation plus the first classify-only analysis slice: FastAPI, Next.js, PostgreSQL with pgvector, Redis/RQ, Ollama wiring, Alembic migrations, committed streetlight procurement seed data, generated frontend API types, structured prompt loading, agent trace logging, and scaffold tests.

## Product Description

InfraLens Georgia is a privacy-preserving infrastructure intelligence tool for analyzing Georgian municipal streetlight incidents. The product combines a FastAPI backend, Next.js frontend, PostgreSQL/pgvector retrieval layer, Redis/RQ background jobs, and local Ollama models to support an end-to-end workflow: submit a civic report, classify the infrastructure issue, retrieve relevant public procurement evidence, generate a bilingual incident brief, and inspect the trace behind the result. It is built as a production-style modular monolith that demonstrates grounded AI analysis without hosted LLM APIs, paid cloud dependencies, maps, auth, or multi-tenant complexity in v1.

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

## Current Boundaries

This implementation supports incident intake and classify-only local analysis. It intentionally does not yet implement RAG-backed evidence retrieval inside the analysis worker, bilingual brief generation, citation grounding, LangGraph orchestration, eval execution, or the complete incident workflow. Those features should be added in later milestones using the module boundaries documented in `docs/architecture.md`.
