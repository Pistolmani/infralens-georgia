from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.rag.retrieval import RetrievalResult

DEFAULT_K = 60
DEFAULT_TOP_N = 5


@dataclass(frozen=True)
class FusedResult:
    chunk_id: uuid.UUID
    rrf_score: float
    rank_per_retriever: dict[str, int]
    retrieval: RetrievalResult


def reciprocal_rank_fusion(
    vector_results: list[RetrievalResult],
    text_results: list[RetrievalResult],
    k: int = DEFAULT_K,
    top_n: int = DEFAULT_TOP_N,
) -> list[FusedResult]:
    scores: dict[uuid.UUID, float] = {}
    ranks: dict[uuid.UUID, dict[str, int]] = {}
    representative: dict[uuid.UUID, RetrievalResult] = {}

    for results in (vector_results, text_results):
        for result in results:
            scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + 1.0 / (k + result.rank)
            chunk_ranks = ranks.setdefault(result.chunk_id, {})
            chunk_ranks[result.source] = result.rank
            existing = representative.get(result.chunk_id)
            if existing is None or result.rank < existing.rank:
                representative[result.chunk_id] = result

    fused = [
        FusedResult(
            chunk_id=chunk_id,
            rrf_score=score,
            rank_per_retriever=dict(ranks[chunk_id]),
            retrieval=representative[chunk_id],
        )
        for chunk_id, score in scores.items()
    ]

    fused.sort(key=lambda f: (-f.rrf_score, str(f.chunk_id)))
    return fused[:top_n]
