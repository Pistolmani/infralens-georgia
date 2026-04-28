from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

# Calibrated such that a chunk ranked #1 in both vector and FTS retrievers maps to confidence 1.0.
# Max RRF score with k=60 is 2 * 1/(60+1) ≈ 0.0328, so dividing by 0.03 caps and clamps.
CITATION_CALIBRATION_SCORE = 0.03


@dataclass(frozen=True)
class CitationViolation:
    claimed_chunk_id: uuid.UUID
    reason: Literal["chunk_not_in_top_5"]


def validate_citations(
    claimed_chunk_ids: Iterable[uuid.UUID],
    top5_chunk_ids: set[uuid.UUID],
) -> list[CitationViolation]:
    violations: list[CitationViolation] = []
    for chunk_id in claimed_chunk_ids:
        if chunk_id not in top5_chunk_ids:
            violations.append(
                CitationViolation(claimed_chunk_id=chunk_id, reason="chunk_not_in_top_5")
            )
    return violations


def compute_retrieval_confidence(top_chunk_rrf_score: float | None) -> float:
    if top_chunk_rrf_score is None or top_chunk_rrf_score <= 0:
        return 0.0
    return min(1.0, top_chunk_rrf_score / CITATION_CALIBRATION_SCORE)
