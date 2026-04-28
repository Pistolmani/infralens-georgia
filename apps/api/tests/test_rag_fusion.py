from __future__ import annotations

import uuid

from app.rag.fusion import DEFAULT_K, reciprocal_rank_fusion
from app.rag.retrieval import RetrievalResult


def _make_result(chunk_id: uuid.UUID, rank: int, source: str, score: float = 1.0) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id=uuid.uuid4(),
        rank=rank,
        score=score,
        chunk_text=f"chunk {chunk_id}",
        chunk_metadata={},
        source=source,  # type: ignore[arg-type]
    )


def test_rrf_uses_k_60_default() -> None:
    chunk = uuid.uuid4()
    fused = reciprocal_rank_fusion(
        vector_results=[_make_result(chunk, rank=1, source="vector")],
        text_results=[],
    )
    expected = 1.0 / (DEFAULT_K + 1)
    assert len(fused) == 1
    assert fused[0].rrf_score == expected


def test_rrf_score_combines_both_retrievers() -> None:
    chunk_in_both = uuid.uuid4()
    chunk_in_one = uuid.uuid4()

    fused = reciprocal_rank_fusion(
        vector_results=[
            _make_result(chunk_in_both, rank=1, source="vector"),
            _make_result(chunk_in_one, rank=2, source="vector"),
        ],
        text_results=[
            _make_result(chunk_in_both, rank=1, source="text"),
        ],
    )

    by_id = {f.chunk_id: f for f in fused}
    assert by_id[chunk_in_both].rrf_score > by_id[chunk_in_one].rrf_score
    assert by_id[chunk_in_both].rank_per_retriever == {"vector": 1, "text": 1}
    assert by_id[chunk_in_one].rank_per_retriever == {"vector": 2}


def test_rrf_returns_top_n_only() -> None:
    chunks = [uuid.uuid4() for _ in range(30)]
    vector = [_make_result(c, rank=i + 1, source="vector") for i, c in enumerate(chunks)]
    text = [_make_result(c, rank=i + 1, source="text") for i, c in enumerate(reversed(chunks))]

    fused = reciprocal_rank_fusion(vector_results=vector, text_results=text, top_n=5)

    assert len(fused) == 5


def test_rrf_deterministic_tie_break() -> None:
    chunk_a = uuid.UUID("00000000-0000-0000-0000-000000000001")
    chunk_b = uuid.UUID("00000000-0000-0000-0000-000000000002")

    fused = reciprocal_rank_fusion(
        vector_results=[
            _make_result(chunk_b, rank=1, source="vector"),
            _make_result(chunk_a, rank=1, source="vector"),
        ],
        text_results=[],
    )

    assert [f.chunk_id for f in fused] == [chunk_a, chunk_b]


def test_rrf_handles_empty_retrievers() -> None:
    assert reciprocal_rank_fusion([], []) == []

    chunk = uuid.uuid4()
    only_vector = reciprocal_rank_fusion(
        vector_results=[_make_result(chunk, rank=1, source="vector")],
        text_results=[],
    )
    assert len(only_vector) == 1


def test_rrf_sorted_descending_by_score() -> None:
    chunks = [uuid.uuid4() for _ in range(5)]
    fused = reciprocal_rank_fusion(
        vector_results=[_make_result(c, rank=i + 1, source="vector") for i, c in enumerate(chunks)],
        text_results=[],
    )
    scores = [f.rrf_score for f in fused]
    assert scores == sorted(scores, reverse=True)
