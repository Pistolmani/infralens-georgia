from __future__ import annotations

from alembic import op

revision = "0002_unaccent_tsv"
down_revision = "0001_initial_v1_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION immutable_unaccent(text)
            RETURNS text
            LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
            AS $$ SELECT public.unaccent('public.unaccent', $1) $$
        """
    )

    op.execute("DROP INDEX IF EXISTS ix_document_chunks_tsv_gin")
    op.execute("ALTER TABLE document_chunks DROP COLUMN tsv")
    op.execute(
        """
        ALTER TABLE document_chunks ADD COLUMN tsv tsvector
            GENERATED ALWAYS AS (
                to_tsvector('simple', immutable_unaccent(coalesce(chunk_text, '')))
            ) STORED
        """
    )
    op.execute("CREATE INDEX ix_document_chunks_tsv_gin ON document_chunks USING gin (tsv)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_tsv_gin")
    op.execute("ALTER TABLE document_chunks DROP COLUMN tsv")
    op.execute(
        """
        ALTER TABLE document_chunks ADD COLUMN tsv tsvector
            GENERATED ALWAYS AS (
                to_tsvector('simple', coalesce(chunk_text, ''))
            ) STORED
        """
    )
    op.execute("CREATE INDEX ix_document_chunks_tsv_gin ON document_chunks USING gin (tsv)")
    op.execute("DROP FUNCTION IF EXISTS immutable_unaccent(text)")
