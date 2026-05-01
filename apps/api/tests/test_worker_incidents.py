from __future__ import annotations

import uuid
from contextlib import contextmanager

from app.llmops.ollama import ReasoningResponse
from app.models.tables import AgentRun, Incident
from app.workers.incidents import analyze_incident


class FakeWorkerSession:
    def __init__(self, incident: Incident) -> None:
        self.incident = incident
        self.agent_runs: list[AgentRun] = []
        self.commits: list[tuple[str, str | None]] = []
        self.closed = False

    def add(self, item: object) -> None:
        if isinstance(item, AgentRun):
            self.agent_runs.append(item)
            return
        raise AssertionError(f"Unexpected add: {item!r}")

    def flush(self) -> None:
        return None

    def get(self, model: type[Incident], incident_id: uuid.UUID) -> Incident:
        assert model is Incident
        assert incident_id == self.incident.id
        return self.incident

    def commit(self) -> None:
        self.commits.append((self.incident.status, self.incident.failure_details))

    def close(self) -> None:
        self.closed = True


class FakeOllamaReasoningClient:
    model = "test-reasoning-model"
    responses: list[str] = []

    def __init__(self, *_: object) -> None:
        self._responses = list(self.responses)

    def __enter__(self) -> FakeOllamaReasoningClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def generate_json(self, prompt: str, temperature: float) -> ReasoningResponse:
        assert prompt
        assert temperature == 0.0
        return ReasoningResponse(text=self._responses.pop(0), raw_response={})


def test_analyze_incident_persists_classify_only_result(monkeypatch) -> None:
    incident = Incident(
        id=uuid.uuid4(),
        original_text="Streetlights are out on Rustaveli Avenue.",
        extracted_entities={},
        status="queued",
        needs_review=False,
        failure_details="Previous failure",
    )
    session = FakeWorkerSession(incident)
    FakeOllamaReasoningClient.responses = [
        """
        {
          "normalized_text": "Streetlights are out on Rustaveli Avenue.",
          "detected_language": "en",
          "location_text": "Rustaveli Avenue",
          "entities": {
            "street_names": ["Rustaveli Avenue"],
            "agencies": [],
            "procurement_terms": [],
            "dates": [],
            "infrastructure_objects": ["streetlights"],
            "other": []
          },
          "extract_conf": 0.9
        }
        """,
        """
        {
          "issue_type": "streetlight",
          "severity": "medium",
          "rationale": "The report describes streetlights being out.",
          "classify_conf": 0.8
        }
        """,
    ]

    @contextmanager
    def fake_scope():
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr("app.workers.incidents.session_scope", fake_scope)
    monkeypatch.setattr("app.workers.incidents.OllamaReasoningClient", FakeOllamaReasoningClient)

    analyze_incident(str(incident.id))

    assert session.commits[0] == ("analyzing", None)
    assert session.commits[-1] == ("analyzed", None)
    assert incident.detected_language == "en"
    assert incident.normalized_text == "Streetlights are out on Rustaveli Avenue."
    assert incident.extracted_location_text == "Rustaveli Avenue"
    assert incident.extracted_entities["street_names"] == ["Rustaveli Avenue"]
    assert incident.issue_type == "streetlight"
    assert incident.severity == "medium"
    assert str(incident.confidence) == "0.8"
    assert incident.needs_review is False
    assert [row.node_name for row in session.agent_runs] == ["ExtractEntities", "ClassifyIncident"]
    assert [row.status for row in session.agent_runs] == ["success", "success"]
    assert session.closed is True


def test_analyze_incident_marks_failed_after_validation_retry(monkeypatch) -> None:
    incident = Incident(
        id=uuid.uuid4(),
        original_text="Streetlight outage",
        extracted_entities={},
        status="queued",
        needs_review=False,
    )
    session = FakeWorkerSession(incident)
    FakeOllamaReasoningClient.responses = ["not json", "still not json"]

    @contextmanager
    def fake_scope():
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr("app.workers.incidents.session_scope", fake_scope)
    monkeypatch.setattr("app.workers.incidents.OllamaReasoningClient", FakeOllamaReasoningClient)

    analyze_incident(str(incident.id))

    assert session.commits[0] == ("analyzing", None)
    assert incident.status == "analysis_failed"
    assert "ExtractEntities returned invalid JSON after correction retry" in incident.failure_details
    assert len(session.agent_runs) == 1
    assert session.agent_runs[0].node_name == "ExtractEntities"
    assert session.agent_runs[0].status == "failed"
    assert session.closed is True
