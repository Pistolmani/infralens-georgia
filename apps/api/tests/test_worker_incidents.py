from __future__ import annotations

import uuid

from app.models.tables import Incident
from app.workers.incidents import ANALYSIS_NOT_IMPLEMENTED_MESSAGE, analyze_incident


class FakeWorkerSession:
    def __init__(self, incident: Incident) -> None:
        self.incident = incident
        self.commits: list[tuple[str, str | None]] = []
        self.closed = False

    def get(self, model: type[Incident], incident_id: uuid.UUID) -> Incident:
        assert model is Incident
        assert incident_id == self.incident.id
        return self.incident

    def commit(self) -> None:
        self.commits.append((self.incident.status, self.incident.failure_details))

    def close(self) -> None:
        self.closed = True


def test_analyze_incident_placeholder_fails_visibly(monkeypatch) -> None:
    incident = Incident(
        id=uuid.uuid4(),
        original_text="Streetlight outage",
        extracted_entities={},
        status="queued",
        needs_review=False,
    )
    session = FakeWorkerSession(incident)

    monkeypatch.setattr("app.workers.incidents.SessionLocal", lambda: session)

    analyze_incident(str(incident.id))

    assert session.commits == [
        ("analyzing", None),
        ("analysis_failed", ANALYSIS_NOT_IMPLEMENTED_MESSAGE),
    ]
    assert session.closed is True

