from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    rrf_score: float
    rank_per_retriever: dict[str, int]
    text_preview: str
    metadata: dict


class SearchResponse(BaseModel):
    query: str
    results: list[SearchHit] = Field(default_factory=list)
    retrieval_confidence: float
