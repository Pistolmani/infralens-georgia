0. Open Questions

No blocking open questions.

1. Architecture Overview

InfraLens Georgia is a production-style, local-first portfolio app for analyzing Georgian municipal infrastructure reports. The v1 system focuses on one fully exercised issue type: streetlights. It accepts Georgian or English free-text reports, extracts the relevant entities, classifies the issue, retrieves supporting public evidence from committed procurement/OCDS seed data, generates a bilingual incident brief, verifies citation support, and persists traces and eval results.

This document guides Milestone 1 implementation. The build spec remains the authoritative source of truth if any conflict appears.

The architecture is a pragmatic modular monolith with a Next.js frontend and a FastAPI backend. The backend owns API routing, ingestion, RAG, LangGraph orchestration, LLMOps trace logging, eval execution, and background jobs. PostgreSQL 16 with pgvector stores application data, seed documents, chunks, embeddings, traces, and eval records. Redis + RQ runs long tasks such as ingestion, incident analysis, and evals. Ollama is the only LLM runtime in v1.

The system is not a chatbot. The main user workflow is incident analysis: submit a report, run analysis, inspect the result, and inspect the trace. The portfolio value comes from explicit system boundaries, local models, structured LLM output, validated agent nodes, hybrid retrieval, citation enforcement, traceability, and reproducible Docker Compose deployment.

v1 intentionally avoids user auth, multi-tenancy, hosted LLM APIs, PostGIS, spatial queries, map views, Askgov ingestion, rerankers, Phoenix/OpenTelemetry, and extra dashboard pages. These exclusions are not placeholders for Milestone 1; they are hard non-goals for v1.

2. Runtime/Container Diagram In Text

Runtime services:

- `web`: Next.js 14+ App Router, TypeScript, Tailwind. Calls the FastAPI API using generated OpenAPI types.
- `api`: FastAPI application running Python 3.12. Serves HTTP endpoints, validates Pydantic schemas, enqueues RQ jobs, and performs lightweight reads.
- `worker`: Python RQ worker using the same backend codebase. Executes ingestion, incident analysis, and eval jobs.
- `postgres`: PostgreSQL 16 with pgvector enabled. Stores incidents, documents, chunks, embeddings, traces, and eval data.
- `redis`: Queue broker for RQ.
- `ollama`: Local model runtime. Hosts the configured reasoning model, default `qwen3:1.7b`, and the configured embedding model, default `bge-m3`.

Text diagram:

`Browser -> web -> api -> postgres`

`api -> redis -> worker -> postgres`

`worker -> ollama`

`api -> ollama` only for health checks or narrowly scoped synchronous diagnostics. Long model calls belong in the worker.

`worker -> seed_data/procurement` for read-only committed seed ingestion.

`make up` starts the runtime. `make bootstrap` pulls Ollama models. `make migrate` applies Alembic migrations. `make codegen` generates frontend API types from the FastAPI OpenAPI schema into `apps/web/lib/api.ts`.

3. Backend Module Boundaries

The backend is a modular monolith. Module names describe ownership; they are not separate services.

- `api/`: FastAPI routers, endpoint dependencies, HTTP request/response wiring, status-code mapping. No business orchestration, ingestion parsing, or retrieval logic lives here.
- `core/`: settings, environment parsing, dependency wiring, logging setup, service health checks, constants that are genuinely global.
- `db/`: SQLAlchemy engine/session setup, base metadata, Alembic integration helpers, transaction utilities.
- `models/`: SQLAlchemy ORM models only. Models are not returned directly from API endpoints.
- `schemas/`: Pydantic v2 request/response schemas, node output schemas, eval schemas, and typed boundaries between modules.
- `ingestion/`: `ProcurementSeedIngestor`, seed-file loading, PII redaction, content hashing, deduplication, normalization, and chunk preparation.
- `rag/`: `embeddings.py`, `retrieval.py`, `fusion.py`, and `citation.py`. Owns embedding calls, vector search, full-text search, Reciprocal Rank Fusion, top-5 selection, and citation enforcement helpers.
- `agents/`: LangGraph state, node implementations, structured LLM calls, graph assembly, confidence aggregation handoff.
- `evals/`: JSONL eval case loading, eval execution, metric calculation, output file writing, DB persistence.
- `llmops/`: prompt YAML loading, prompt versioning, model metadata, `AgentRunLogger`, run trace persistence, validation error recording.
- `workers/`: RQ jobs and background task entry points, including `AnalyzeIncidentTask`.

Do not introduce giant service classes such as `AIService`, `DataService`, `IncidentService`, `Manager`, or `Processor`. Prefer explicit names that describe the narrow responsibility.

All I/O boundaries use Pydantic. Loose dictionaries must not cross module boundaries unless represented by a typed schema. SQLAlchemy models, API schemas, and node schemas stay separate.

4. Frontend Module Boundaries

The frontend contains only four v1 pages:

- Incident Intake: form for Georgian/English report text, optional language hint, and optional location hint if the API schema supports it.
- Incident List: table/list of incidents with status, issue type, severity, confidence, `needs_review`, and created timestamp.
- Incident Detail: canonical view of classification, extracted entities, bilingual brief, citations, status, confidence, and failure details if analysis failed.
- Run Trace: node-by-node trace for a selected incident, including prompt version, model, latency, structured output summary, confidence, validation errors, and retrieved chunk IDs where relevant.

No map page, Evidence Explorer, or Eval Dashboard is included in v1.

Frontend API types are generated with `openapi-typescript` from the FastAPI OpenAPI schema. The generated output path is `apps/web/lib/api.ts`. Frontend code must not hand-write API response types that duplicate backend schemas. If an endpoint shape changes, regenerate types through `make codegen`.

Tailwind is used for UI styling. The design should favor dense operational screens rather than a marketing landing page. The first screen should be the Incident Intake workflow.

5. Database Schema Explanation

The v1 schema uses PostgreSQL 16 and pgvector. No PostGIS extension or spatial column is used.

`incidents` stores user-submitted reports and the latest analysis result. Key fields include original text, language hint/detected language, normalized text, issue type, severity, extracted location text, extracted entities, status, confidence, `needs_review`, bilingual brief fields, timestamps, and failure details. Status values should support at least created, queued, analyzing, analyzed, and analysis_failed.

`documents` stores ingested procurement/OCDS source documents. It records source type, source path or URL, source ID where available, title, agency or buyer if present, procurement identifiers where present, content hash, raw metadata, and timestamps.

`document_chunks` stores chunked text for retrieval. Each row belongs to one document and includes chunk text, token estimate, chunk index, metadata, `embedding vector(1024)`, and a generated/stored `tsv` column for full-text search. The embedding dimension is fixed to 1024 in v1.

`evidence_links` records which chunks support which generated brief claims. It stores incident ID, chunk ID, claim text, citation label, support level (`strong`, `partial`, `weak`), verifier rationale, and timestamps.

`ingestion_runs` records each seed ingestion attempt, status, source path, counts for documents/chunks inserted/skipped, error details, and timing.

`agent_runs` is the LLMOps trace table. It records incident ID, node name, prompt name/version, model, temperature, input summary, output JSON, validation errors, node confidence, latency, retrieved chunk references where relevant, status, and timestamps.

`eval_cases` stores imported JSONL cases or metadata for cases loaded from `eval_cases/civic_reports_v1.jsonl`.

`eval_runs` stores aggregate eval execution metadata, including run status, started/finished timestamps, model/prompt versions, and aggregate metrics.

`eval_results` stores per-case metric results and failure details.

Required indexes:

- HNSW index on `document_chunks.embedding` using `vector_cosine_ops`.
- GIN index on `document_chunks.tsv`.
- Index on `incidents(status, created_at)`.
- Index on `agent_runs(incident_id)`.

6. Data Flow

Ingestion flow:

1. Operator calls `POST /ingest/procurement` with `X-Ingest-Key`.
2. API validates the ingest key from env and enqueues an RQ ingestion job.
3. Worker creates an `ingestion_runs` record.
4. `ProcurementSeedIngestor` reads committed files under `seed_data/procurement/`.
5. Ingestion normalizes procurement/OCDS fields into document records, applies PII redaction where relevant, computes content hashes, and deduplicates.
6. Chunk preparation creates 500-800 token chunks with 80-token overlap, respecting sentence boundaries where practical.
7. Worker embeds chunks through Ollama using `OLLAMA_EMBED_MODEL`, validates 1024 dimensions, stores chunks and embeddings, updates run counts.
8. If any adapter cannot parse a file, the ingestion run records a visible error. No fake successful ingestion.

Incident analysis flow:

1. User creates an incident through `POST /incidents`.
2. User or UI calls `POST /incidents/{id}/analyze`.
3. API marks the incident queued and enqueues `AnalyzeIncidentTask`.
4. Worker marks incident analyzing and runs the LangGraph workflow.
5. Each node writes an `agent_runs` record with structured output, validation result, confidence, and latency.
6. The graph writes final incident fields, confidence, `needs_review`, citations, and status.
7. If invalid JSON remains after one correction retry, the incident becomes `analysis_failed`.

Retrieval flow:

1. RetrieveEvidence receives normalized report text, extracted entities, classification, and location text.
2. `HybridRetriever` runs vector search top-20 and full-text search top-20.
3. Full-text search uses Postgres `simple` configuration plus `unaccent`.
4. `RrfFusion` fuses results with `score = sum(1 / (60 + rank))`.
5. Final top-5 chunks are stored in graph state and passed to GenerateBrief.
6. GenerateBrief may only cite those top-5 chunks.

Eval flow:

1. Eval cases are loaded from `eval_cases/civic_reports_v1.jsonl`.
2. Early implementation starts with 3 cases; v1 expands to about 20.
3. `POST /evals/run` enqueues eval execution.
4. Worker runs the same incident pipeline against each case, records per-case results, calculates aggregate metrics, writes `eval_runs/<timestamp>.json`, and persists results to DB.
5. `GET /evals/latest` returns the latest aggregate run.

7. LangGraph Workflow Design

Graph nodes are exactly:

ExtractEntities -> ClassifyIncident -> RetrieveEvidence -> GenerateBrief -> VerifyGrounding

`NormalizeInput` is not a graph node. It is a helper called inside ExtractEntities.

State transition table:

| Step | Node | Success Next | Failure Behavior |
| --- | --- | --- | --- |
| 1 | ExtractEntities | ClassifyIncident | Retry invalid JSON once; then `analysis_failed` |
| 2 | ClassifyIncident | RetrieveEvidence | Retry invalid JSON once; then `analysis_failed` |
| 3 | RetrieveEvidence | GenerateBrief | If retrieval errors, `analysis_failed`; if weak retrieval, continue with low confidence |
| 4 | GenerateBrief | VerifyGrounding | Retry invalid JSON once; then `analysis_failed` |
| 5 | VerifyGrounding | Finalize incident | Persist support levels, confidence, `needs_review` |

Node responsibilities:

ExtractEntities reads incident text, language hint, and optional location hint. It calls NormalizeInput internally, then uses structured LLM output to write normalized text, detected language, location text, entities, and `extract_conf`. Entities may include street names, agencies, procurement terms, dates, and infrastructure objects. Missing `node_confidence` becomes `0.0` and is logged.

ClassifyIncident reads normalized text, extracted entities, and language. It writes issue type, severity, classification rationale, and `classify_conf`. Streetlights are the optimized category. Other categories may be recognized but are not tuned.

RetrieveEvidence reads normalized text, extracted entities, issue type, severity, and location text. It writes vector results, full-text results, fused top-5 chunks, retrieval scores, and `retrieval_conf = min(1.0, top_chunk_rrf_score / 0.03)`. It does not call the reasoning LLM.

GenerateBrief reads the incident fields and retrieved top-5 chunks. It writes structured bilingual Georgian/English brief fields, recommended action, missing information, claim list, citation references, and `generate_conf`. It must not cite anything outside the retrieved top-5.

VerifyGrounding reads generated claims, citations, and retrieved chunks. It applies the code-level citation support rubric and may use structured LLM assistance only after deterministic checks prepare the evidence. It writes `strong`, `partial`, or `weak` support per claim, evidence links, `grounding_conf`, final confidence, and `needs_review`.

Overall incident confidence is:

`min(extract_conf, classify_conf, retrieval_conf, grounding_conf)`

If any confidence is missing or invalid, use `0.0` and persist the validation issue. If final confidence is below `0.6`, set `needs_review = true`.

8. RAG Retrieval Design

Retrieval uses committed procurement/OCDS seed data only. No Askgov, web scraping, or external live procurement calls are part of v1 runtime.

Chunking produces 500-800 token chunks with 80-token overlap. Sentence-boundary awareness is required where practical so citations do not split claims awkwardly. Each chunk keeps source metadata sufficient to display citation labels and trace back to the source document.

Embeddings are generated through Ollama. The default env var is `OLLAMA_EMBED_MODEL=bge-m3`. The embedding adapter must validate that the returned vector has exactly 1024 dimensions. Any other dimension is a visible configuration error because `document_chunks.embedding` is `vector(1024)`.

Vector retrieval returns top-20 by cosine distance using pgvector. Full-text retrieval returns top-20 using Postgres `simple` config plus `unaccent`. Both retrievers return typed retrieval results with chunk ID, rank, score, text preview, and metadata.

RRF fusion uses `k = 60`:

`score(chunk) = sum over retrievers [1 / (60 + rank_in_retriever)]`

The final top-5 fused chunks are the only chunks passed to GenerateBrief. Citation enforcement rejects or flags any generated citation that references a chunk outside that top-5.

The retrieval eval metric is named `keyword_hit_rate@5`.

9. LLMOps/Tracing Design

Prompts live in `/prompts` as YAML files. Long prompts must not be hardcoded in Python. Each prompt file includes name, version, model, temperature, output schema reference, and prompt text.

`PromptRegistry` loads prompts, validates required fields, and provides prompt metadata to agent nodes. Agent nodes record prompt name and version in `agent_runs`, making output reproducible and comparable across prompt revisions.

Every LLM output must be structured JSON. Every LLM output must be validated with Pydantic. Invalid JSON handling is uniform:

1. Try parsing.
2. Retry once with a correction prompt.
3. If still invalid, persist validation errors in `agent_runs`.
4. Mark the incident as `analysis_failed`.

`AgentRunLogger` writes a row per node execution. It records node status, input summary, output JSON if available, validation errors, confidence, latency, prompt metadata, and model metadata. Trace data should be useful from the Run Trace page without exposing excessive raw prompt text.

10. API Contract Summary

`GET /healthz` returns structured health for database, redis, and ollama. Status is `ok` when all are reachable and `degraded` when a noncritical dependency such as Ollama is unreachable.

`POST /incidents` creates an incident from report text and optional hints. It returns the created incident summary.

`POST /incidents/{id}/analyze` enqueues analysis. It returns queued status and job metadata.

`GET /incidents/{id}` returns incident detail, bilingual brief, citations, status, confidence, and failure details.

`GET /incidents` returns a paginated or bounded list suitable for the Incident List page.

`GET /search` searches ingested evidence using the same retrieval stack or a read-only subset of it. It must not become an Evidence Explorer page in v1.

`POST /ingest/procurement` requires `X-Ingest-Key: <env var>`, enqueues procurement seed ingestion, and returns run/job metadata.

`POST /evals/run` enqueues eval execution.

`GET /evals/latest` returns latest eval aggregate.

If `/ingest/askgov` exists, it must return `501 Not Implemented`.

Read endpoints stay open in v1. Ingest endpoints require the ingest key.

11. Failure Handling Strategy

No silent failures. No bare `except`. Exceptions are caught at module boundaries where they can be logged, traced, and converted into explicit statuses.

Configuration failures, such as an embedding model returning non-1024-dimensional vectors, fail visibly and stop the relevant ingestion or analysis task. They are not patched by changing schema or padding vectors.

Ollama unreachable: `/healthz` reports degraded. Ingestion or analysis requiring Ollama fails the job visibly unless the operation does not need model access.

Redis unreachable: `/healthz` reports degraded; enqueue endpoints return an appropriate error because background jobs cannot be scheduled.

Database unreachable: `/healthz` reports degraded or unavailable; most endpoints fail.

Weak evidence is not a system failure. The graph continues, lowers confidence, records weak support, and sets `needs_review` when final confidence is below `0.6`.

Generated citations outside retrieved top-5 are invalid. The verifier records the violation, marks unsupported claims weak, lowers grounding confidence, and may force `needs_review`.

12. Testing Strategy

Unit tests cover settings validation, seed parsing, PII redaction, content hashing, chunking, embedding dimension validation, RRF fusion, citation support classification, prompt registry validation, and Pydantic node schemas.

Integration tests cover Alembic migrations, database session wiring, pgvector availability, Redis enqueue behavior, `/healthz`, procurement ingestion against a tiny fixture, retrieval over seeded chunks, and incident analysis with mocked Ollama responses.

Agent tests validate structured JSON parsing, one correction retry, confidence fallback to `0.0`, and `analysis_failed` transitions.

Frontend tests should be lightweight in v1: type generation check, page rendering smoke tests, and API-client compile checks.

Eval metrics are:

- `category_accuracy`
- `severity_accuracy`
- `keyword_hit_rate@5`
- `citation_support_rate`
- `invalid_json_rate`
- `latency_p50`
- `latency_p95`

Milestone 1 acceptance requires `make test` to exercise available scaffold tests and `make up`/`make migrate` to work locally.

13. Milestone 1 Implementation Plan

Milestone 1 creates the runnable foundation only.

Implement repo structure for the modular monolith, including backend, frontend, prompts, seed data, eval case folders, scripts, and docs. Add Docker Compose with `api`, `web`, `postgres+pgvector`, `redis`, and `ollama`.

Add `bootstrap-ollama.sh` to pull the configured reasoning model from `OLLAMA_REASONING_MODEL`, defaulting to `qwen3:1.7b`, and the configured embedding model from `OLLAMA_EMBED_MODEL`, defaulting to `bge-m3`.

Create FastAPI startup, settings, DB session wiring, Redis health check, Ollama health check, and `GET /healthz` with structured service health.

Create Next.js startup and the minimal app shell needed to confirm the web container runs. Do not implement the full four-page UX in Milestone 1 unless explicitly assigned later.

Create Alembic setup and initial migrations for the v1 tables and required indexes where possible. Migrations must apply cleanly.

Add Makefile targets: `up`, `down`, `migrate`, `seed`, `codegen`, `test`, `eval`, `bootstrap`.

Add `.env.example`, README with local hardware requirements and startup steps, and AGENTS.md with project conventions.

End Milestone 1 with: tests run, what changed, what works, what remains, and what surprised you.

14. Risks And Mitigations

Local hardware may be too small or too slow for larger reasoning models such as `qwen3:4b` or `qwen3:8b` with `bge-m3`. Mitigation: default to `qwen3:1.7b`, keep the reasoning model configurable, document hardware expectations in README, and fail clearly when Ollama cannot load a model. Do not add hosted fallback in v1.

Ollama model naming for `bge-m3` may differ by local registry availability. Mitigation: keep the model configurable through `OLLAMA_EMBED_MODEL`, validate dimensions, and document the expected 1024-dimensional requirement.

Procurement seed data may not contain enough streetlight-specific evidence for strong citations. Mitigation: curate the committed seed subset around streetlight/public lighting examples and let weak evidence produce low confidence rather than fabricated support.

Georgian text quality from the local reasoning model may vary. Mitigation: keep outputs structured, validate every node, include bilingual fields, and measure failures through evals.

Postgres full-text search with `simple` plus `unaccent` is limited for Georgian morphology. Mitigation: treat FTS as one retriever in a hybrid system and rely on embeddings plus RRF to compensate.

15. Explicit V1 Non-Goals

- No PostGIS.
- No spatial queries.
- No map view.
- No Evidence Explorer page.
- No Eval Dashboard page.
- No reranker.
- No Askgov ingestion.
- No Phoenix or OpenTelemetry.
- No hosted LLM APIs.
- No paid cloud dependencies.
- No user auth.
- No multi-tenancy.
- No translation services beyond local model output.
- No municipalities beyond committed seed data.
- No `HumanReviewIfLowConfidence` graph node.
- No chatbot interface.
- No API wrapper-only implementation.
- No hand-written frontend API types.
