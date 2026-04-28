from __future__ import annotations

import uuid

from app.rag.citation import (
    CITATION_CALIBRATION_SCORE,
    compute_retrieval_confidence,
    validate_citations,
)


def test_validate_citations_passes_when_all_in_top5() -> None:
    chunks = {uuid.uuid4() for _ in range(5)}
    violations = validate_citations(claimed_chunk_ids=list(chunks)[:3], top5_chunk_ids=chunks)
    assert violations == []


def test_validate_citations_flags_out_of_top5() -> None:
    top5 = {uuid.uuid4() for _ in range(5)}
    rogue = uuid.uuid4()

    violations = validate_citations(
        claimed_chunk_ids=[next(iter(top5)), rogue],
        top5_chunk_ids=top5,
    )

    assert len(violations) == 1
    assert violations[0].claimed_chunk_id == rogue
    assert violations[0].reason == "chunk_not_in_top_5"


def test_compute_retrieval_confidence_max_at_calibration_point() -> None:
    assert compute_retrieval_confidence(CITATION_CALIBRATION_SCORE) == 1.0


def test_compute_retrieval_confidence_clamps_to_one() -> None:
    assert compute_retrieval_confidence(0.05) == 1.0
    assert compute_retrieval_confidence(1.0) == 1.0


def test_compute_retrieval_confidence_zero_for_no_results() -> None:
    assert compute_retrieval_confidence(None) == 0.0
    assert compute_retrieval_confidence(0.0) == 0.0
    assert compute_retrieval_confidence(-0.1) == 0.0


def test_compute_retrieval_confidence_low_score() -> None:
    result = compute_retrieval_confidence(0.005)
    assert abs(result - (0.005 / CITATION_CALIBRATION_SCORE)) < 1e-9
