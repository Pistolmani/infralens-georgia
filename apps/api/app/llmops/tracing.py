from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.llmops.prompts import Prompt
from app.models.tables import AgentRun


class AgentRunLogger:
    def __init__(self, db: Session) -> None:
        self._db = db

    def log(
        self,
        *,
        incident_id: uuid.UUID,
        node_name: str,
        prompt: Prompt,
        model: str,
        input_summary: str,
        status: str,
        latency_ms: int | None = None,
        output_json: dict | None = None,
        validation_errors: list[dict] | None = None,
        node_confidence: float | None = None,
        retrieved_chunk_refs: list[dict] | None = None,
    ) -> AgentRun:
        row = AgentRun(
            incident_id=incident_id,
            node_name=node_name,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            model=model,
            temperature=Decimal(str(prompt.temperature)),
            input_summary=input_summary,
            output_json=output_json,
            validation_errors=validation_errors or [],
            node_confidence=Decimal(str(node_confidence)) if node_confidence is not None else None,
            latency_ms=latency_ms,
            retrieved_chunk_refs=retrieved_chunk_refs or [],
            status=status,
        )
        self._db.add(row)
        self._db.flush()
        return row
