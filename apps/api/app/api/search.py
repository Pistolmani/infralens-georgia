from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.rag.citation import compute_retrieval_confidence
from app.rag.embeddings import ConfigurationError, OllamaEmbedder
from app.rag.fusion import DEFAULT_TOP_N, reciprocal_rank_fusion
from app.rag.retrieval import HybridRetriever
from app.schemas.search import SearchHit, SearchResponse

router = APIRouter(tags=["search"])

PREVIEW_LENGTH = 200


def get_embedder() -> Generator[OllamaEmbedder, None, None]:
    embedder = OllamaEmbedder()
    try:
        yield embedder
    finally:
        embedder.close()


@router.get("/search", response_model=SearchResponse)
def search(
    db: Annotated[Session, Depends(get_db)],
    embedder: Annotated[OllamaEmbedder, Depends(get_embedder)],
    q: Annotated[str, Query(min_length=1, max_length=500)],
    limit: Annotated[int, Query(ge=1, le=DEFAULT_TOP_N)] = DEFAULT_TOP_N,
) -> SearchResponse:
    retriever = HybridRetriever(db=db, embedder=embedder)

    try:
        vector_results, text_results = retriever.retrieve(q)
    except (httpx.HTTPError, ConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Retrieval unavailable: {exc.__class__.__name__}",
        ) from exc

    fused = reciprocal_rank_fusion(vector_results, text_results, top_n=limit)

    top_score = fused[0].rrf_score if fused else None
    confidence = compute_retrieval_confidence(top_score)

    return SearchResponse(
        query=q,
        results=[
            SearchHit(
                chunk_id=hit.chunk_id,
                document_id=hit.retrieval.document_id,
                rrf_score=hit.rrf_score,
                rank_per_retriever=hit.rank_per_retriever,
                text_preview=hit.retrieval.chunk_text[:PREVIEW_LENGTH],
                metadata=hit.retrieval.chunk_metadata,
            )
            for hit in fused
        ],
        retrieval_confidence=confidence,
    )
