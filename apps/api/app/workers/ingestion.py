from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import session_scope
from app.ingestion.constants import IngestionRunStatus
from app.ingestion.seed import ProcurementSeedIngestor
from app.models.tables import IngestionRun
from app.rag.embeddings import OllamaEmbedder

logger = logging.getLogger(__name__)


def ingest_procurement_seed() -> None:
    settings = get_settings()
    seed_dir = settings.seed_data_dir

    with session_scope() as db:
        run = IngestionRun(
            status=IngestionRunStatus.running.value,
            source_path=str(seed_dir),
            started_at=datetime.now(UTC),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        try:
            with OllamaEmbedder(settings) as embedder:
                ingestor = ProcurementSeedIngestor(db=db, embedder=embedder, seed_dir=seed_dir)
                result = ingestor.ingest()
        except Exception as exc:
            logger.exception("Ingestion job failed")
            _mark_run_failed(db, run, str(exc))
            raise

        run.status = (
            IngestionRunStatus.failed.value
            if result.errors and result.documents_inserted == 0
            else IngestionRunStatus.complete.value
        )
        run.documents_inserted = result.documents_inserted
        run.documents_skipped = result.documents_skipped
        run.chunks_inserted = result.chunks_inserted
        run.error_details = "; ".join(result.errors) if result.errors else None
        run.finished_at = datetime.now(UTC)
        db.commit()

        logger.info(
            "Ingestion run %s: docs_inserted=%d docs_skipped=%d chunks=%d errors=%d",
            run.id,
            result.documents_inserted,
            result.documents_skipped,
            result.chunks_inserted,
            len(result.errors),
        )


def _mark_run_failed(db, run: IngestionRun, message: str) -> None:
    try:
        run.status = IngestionRunStatus.failed.value
        run.error_details = message
        run.finished_at = datetime.now(UTC)
        db.commit()
    except SQLAlchemyError:
        logger.exception("Failed to record ingestion failure for run %s", run.id)
        db.rollback()
