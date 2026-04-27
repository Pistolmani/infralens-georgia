from __future__ import annotations

from alembic import op

revision = "0001_initial_v1_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute(
        """
        CREATE TABLE incidents (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            original_text text NOT NULL,
            language_hint text,
            detected_language text,
            normalized_text text,
            issue_type text,
            severity text,
            extracted_location_text text,
            extracted_entities jsonb NOT NULL DEFAULT '{}'::jsonb,
            status text NOT NULL DEFAULT 'created',
            confidence numeric(4, 3),
            needs_review boolean NOT NULL DEFAULT false,
            brief_ka text,
            brief_en text,
            failure_details text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE documents (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            source_type text NOT NULL,
            source_path text,
            source_url text,
            source_id text,
            title text,
            agency text,
            buyer text,
            procurement_id text,
            content_hash text NOT NULL UNIQUE,
            raw_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE document_chunks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_text text NOT NULL,
            token_estimate integer NOT NULL,
            chunk_index integer NOT NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            embedding vector(1024),
            tsv tsvector GENERATED ALWAYS AS (
                to_tsvector('simple', coalesce(chunk_text, ''))
            ) STORED,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (document_id, chunk_index)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE evidence_links (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
            chunk_id uuid NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
            claim_text text NOT NULL,
            citation_label text NOT NULL,
            support_level text NOT NULL,
            verifier_rationale text,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE ingestion_runs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            status text NOT NULL,
            source_path text,
            documents_inserted integer NOT NULL DEFAULT 0,
            documents_skipped integer NOT NULL DEFAULT 0,
            chunks_inserted integer NOT NULL DEFAULT 0,
            chunks_skipped integer NOT NULL DEFAULT 0,
            error_details text,
            started_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz
        )
        """
    )
    op.execute(
        """
        CREATE TABLE agent_runs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id uuid REFERENCES incidents(id) ON DELETE CASCADE,
            node_name text NOT NULL,
            prompt_name text,
            prompt_version text,
            model text,
            temperature numeric(4, 3),
            input_summary text,
            output_json jsonb,
            validation_errors jsonb NOT NULL DEFAULT '[]'::jsonb,
            node_confidence numeric(4, 3),
            latency_ms integer,
            retrieved_chunk_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
            status text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE eval_cases (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            case_key text NOT NULL UNIQUE,
            source_path text NOT NULL,
            input_json jsonb NOT NULL,
            expected_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE eval_runs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            status text NOT NULL,
            model text,
            prompt_versions jsonb NOT NULL DEFAULT '{}'::jsonb,
            aggregate_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
            output_path text,
            started_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz
        )
        """
    )
    op.execute(
        """
        CREATE TABLE eval_results (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            eval_run_id uuid NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
            eval_case_id uuid REFERENCES eval_cases(id) ON DELETE SET NULL,
            incident_id uuid REFERENCES incidents(id) ON DELETE SET NULL,
            metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
            failure_details text,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    op.execute("CREATE INDEX ix_incidents_status_created_at ON incidents (status, created_at)")
    op.execute("CREATE INDEX ix_agent_runs_incident_id ON agent_runs (incident_id)")
    op.execute("CREATE INDEX ix_document_chunks_tsv_gin ON document_chunks USING gin (tsv)")
    op.execute(
        """
        CREATE INDEX ix_document_chunks_embedding_hnsw
        ON document_chunks USING hnsw (embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_tsv_gin")
    op.execute("DROP INDEX IF EXISTS ix_agent_runs_incident_id")
    op.execute("DROP INDEX IF EXISTS ix_incidents_status_created_at")
    op.execute("DROP TABLE IF EXISTS eval_results")
    op.execute("DROP TABLE IF EXISTS eval_runs")
    op.execute("DROP TABLE IF EXISTS eval_cases")
    op.execute("DROP TABLE IF EXISTS agent_runs")
    op.execute("DROP TABLE IF EXISTS ingestion_runs")
    op.execute("DROP TABLE IF EXISTS evidence_links")
    op.execute("DROP TABLE IF EXISTS document_chunks")
    op.execute("DROP TABLE IF EXISTS documents")
    op.execute("DROP TABLE IF EXISTS incidents")

