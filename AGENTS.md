# InfraLens Georgia Conventions

InfraLens is a local-first modular monolith. Keep the architecture in `docs/architecture.md` as the source of truth for v1 boundaries.

- Keep hosted LLM APIs, PostGIS, map views, Askgov ingestion, rerankers, auth, and multi-tenancy out of v1.
- Keep `NormalizeInput` as a helper inside `ExtractEntities`, not as a LangGraph node.
- Use Pydantic schemas at module boundaries. Do not pass loose dictionaries between modules.
- Do not return SQLAlchemy models directly from API endpoints.
- Put long prompts in `prompts/` YAML files, not Python strings.
- Generate frontend API types into `apps/web/lib/api.ts` with `make codegen`; do not hand-write duplicated API response types.
- Prefer narrow module names over broad service classes.

