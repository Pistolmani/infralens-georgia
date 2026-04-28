from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ingestion.chunker import chunk_text
from app.ingestion.constants import DocumentSourceType
from app.ingestion.normalizer import normalize_ocds
from app.ingestion.pii import redact_pii
from app.models.tables import Document, DocumentChunk
from app.rag.embeddings import ConfigurationError, OllamaEmbedder

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    documents_inserted: int = 0
    documents_skipped: int = 0
    chunks_inserted: int = 0
    errors: list[str] = field(default_factory=list)


class ProcurementSeedIngestor:
    def __init__(
        self,
        db: Session,
        embedder: OllamaEmbedder,
        seed_dir: Path,
    ) -> None:
        self._db = db
        self._embedder = embedder
        self._seed_dir = seed_dir

    def ingest(self) -> IngestionResult:
        result = IngestionResult()

        json_files = sorted(self._seed_dir.glob("*.json"))
        if not json_files:
            logger.warning("No JSON files found in %s", self._seed_dir)
            return result

        for path in json_files:
            try:
                self._ingest_file(path, result)
            except (json.JSONDecodeError, OSError, httpx.HTTPError, ConfigurationError, SQLAlchemyError) as exc:
                msg = f"{path.name}: {exc.__class__.__name__}: {exc}"
                logger.error("Error ingesting %s: %s", path.name, exc)
                result.errors.append(msg)
                self._db.rollback()

        return result

    def _ingest_file(self, path: Path, result: IngestionResult) -> None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        doc = normalize_ocds(raw, str(path))

        redacted_text = redact_pii(doc.description_text)
        content_hash = hashlib.sha256(redacted_text.encode()).hexdigest()

        existing = self._db.execute(
            select(Document).where(Document.content_hash == content_hash)
        ).scalar_one_or_none()

        if existing is not None:
            logger.info("Skipping %s — content hash already ingested", path.name)
            result.documents_skipped += 1
            return

        document = Document(
            source_type=DocumentSourceType.procurement_ocds.value,
            source_path=str(path),
            source_id=doc.source_id,
            title=doc.title,
            agency=doc.agency,
            buyer=doc.buyer,
            procurement_id=doc.procurement_id,
            content_hash=content_hash,
            raw_metadata=doc.raw_metadata,
        )
        self._db.add(document)
        self._db.flush()
        result.documents_inserted += 1

        chunks = chunk_text(redacted_text)
        if not chunks:
            self._db.commit()
            return

        embeddings = self._embedder.embed_batch([chunk.text for chunk in chunks])

        for chunk, embedding in zip(chunks, embeddings, strict=True):
            db_chunk = DocumentChunk(
                document_id=document.id,
                chunk_text=chunk.text,
                token_estimate=chunk.token_count,
                chunk_index=chunk.index,
                chunk_metadata={
                    "source_path": str(path),
                    "source_id": doc.source_id,
                    "title": doc.title,
                },
                embedding=embedding,
            )
            self._db.add(db_chunk)
            result.chunks_inserted += 1

        self._db.commit()
        logger.info("Ingested %s: %d chunk(s)", path.name, len(chunks))
