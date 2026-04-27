from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.db.session import SessionLocal
from app.models.tables import Incident

ANALYSIS_NOT_IMPLEMENTED_MESSAGE = "Incident analysis pipeline is not implemented yet."


def analyze_incident(incident_id: str) -> None:
    db = SessionLocal()
    try:
        incident = db.get(Incident, uuid.UUID(incident_id))
        if incident is None:
            return

        incident.status = "analyzing"
        incident.updated_at = datetime.now(UTC)
        db.commit()

        incident.status = "analysis_failed"
        incident.failure_details = ANALYSIS_NOT_IMPLEMENTED_MESSAGE
        incident.updated_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()

