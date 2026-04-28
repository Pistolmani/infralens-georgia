from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from app.rag.embeddings import EXPECTED_DIMENSIONS, OllamaEmbedder

RetrieverSource = Literal["vector", "text"]


@dataclass(frozen=True)
class RetrievalResult:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    rank: int
    score: float
    chunk_text: str
    chunk_metadata: dict
    source: RetrieverSource


_VECTOR_QUERY = text(
    """
    SELECT
        id,
        document_id,
        chunk_text,
        metadata,
        1 - (embedding <=> :query_vector) AS score
    FROM document_chunks
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> :query_vector
    LIMIT :limit
    """
).bindparams(bindparam("query_vector", type_=Vector(EXPECTED_DIMENSIONS)))

_TEXT_QUERY = text(
    """
    SELECT
        id,
        document_id,
        chunk_text,
        metadata,
        ts_rank_cd(tsv, plainto_tsquery('simple', immutable_unaccent(:query_text))) AS score
    FROM document_chunks
    WHERE tsv @@ plainto_tsquery('simple', immutable_unaccent(:query_text))
    ORDER BY score DESC
    LIMIT :limit
    """
)


class HybridRetriever:
    def __init__(self, db: Session, embedder: OllamaEmbedder) -> None:
        self._db = db
        self._embedder = embedder

    def vector_search(self, query_text: str, limit: int = 20) -> list[RetrievalResult]:
        embedding = self._embedder.embed(query_text)
        rows = self._db.execute(
            _VECTOR_QUERY,
            {"query_vector": embedding, "limit": limit},
        ).all()
        return [_row_to_result(row, rank=i + 1, source="vector") for i, row in enumerate(rows)]

    def text_search(self, query_text: str, limit: int = 20) -> list[RetrievalResult]:
        rows = self._db.execute(
            _TEXT_QUERY,
            {"query_text": query_text, "limit": limit},
        ).all()
        return [_row_to_result(row, rank=i + 1, source="text") for i, row in enumerate(rows)]

    def retrieve(
        self,
        query_text: str,
        limit_per_retriever: int = 20,
    ) -> tuple[list[RetrievalResult], list[RetrievalResult]]:
        return (
            self.vector_search(query_text, limit=limit_per_retriever),
            self.text_search(query_text, limit=limit_per_retriever),
        )


def _row_to_result(row: Row, rank: int, source: RetrieverSource) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=row.id,
        document_id=row.document_id,
        rank=rank,
        score=float(row.score),
        chunk_text=row.chunk_text,
        chunk_metadata=row.metadata or {},
        source=source,
    )
