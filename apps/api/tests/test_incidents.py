from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.models.tables import Incident


class FakeScalarResult:
    def __init__(self, items: list[Incident]) -> None:
        self.items = items

    def scalars(self) -> FakeScalarResult:
        return self

    def all(self) -> list[Incident]:
        return self.items


class FakeIncidentSession:
    def __init__(self) -> None:
        self.incidents: dict[uuid.UUID, Incident] = {}
        self.write_count = 0

    def add(self, incident: Incident) -> None:
        self.write_count += 1
        now = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=self.write_count)
        incident.id = uuid.uuid4()
        incident.created_at = now
        incident.updated_at = now
        self.incidents[incident.id] = incident

    def commit(self) -> None:
        return None

    def refresh(self, incident: Incident) -> None:
        return None

    def get(self, model: type[Incident], incident_id: uuid.UUID) -> Incident | None:
        assert model is Incident
        return self.incidents.get(incident_id)

    def execute(self, statement: object) -> FakeScalarResult:
        items = sorted(
            self.incidents.values(),
            key=lambda incident: incident.created_at,
            reverse=True,
        )
        offset = _select_clause_value(getattr(statement, "_offset_clause", None)) or 0
        limit = _select_clause_value(getattr(statement, "_limit_clause", None))
        if limit is not None:
            items = items[offset : offset + limit]
        else:
            items = items[offset:]
        return FakeScalarResult(items)


def _select_clause_value(clause: object | None) -> int | None:
    if clause is None:
        return None
    value = getattr(clause, "value", clause)
    return int(value)


@pytest.fixture
def incident_client() -> Generator[tuple[TestClient, FakeIncidentSession], None, None]:
    session = FakeIncidentSession()

    def override_get_db() -> Generator[FakeIncidentSession, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, session
    app.dependency_overrides.pop(get_db, None)


def test_create_incident_persists_initial_fields(incident_client: tuple[TestClient, FakeIncidentSession]) -> None:
    client, session = incident_client

    response = client.post(
        "/incidents",
        json={
            "report_text": "  Streetlights are out on Rustaveli Avenue.  ",
            "language_hint": "KA",
            "location_hint": " Rustaveli Avenue ",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["original_text"] == "Streetlights are out on Rustaveli Avenue."
    assert body["language_hint"] == "ka"
    assert body["status"] == "created"
    assert body["needs_review"] is False

    incident = next(iter(session.incidents.values()))
    assert incident.original_text == "Streetlights are out on Rustaveli Avenue."
    assert incident.language_hint == "ka"
    assert incident.extracted_location_text == "Rustaveli Avenue"


def test_list_incidents_returns_bounded_summaries(incident_client: tuple[TestClient, FakeIncidentSession]) -> None:
    client, _session = incident_client
    client.post("/incidents", json={"report_text": "First report"})
    second = client.post("/incidents", json={"report_text": "Second report"}).json()

    response = client.get("/incidents?limit=1&offset=0")

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 1
    assert body["offset"] == 0
    assert body["items"] == [second]


def test_get_incident_detail_returns_full_shape(incident_client: tuple[TestClient, FakeIncidentSession]) -> None:
    client, _session = incident_client
    created = client.post(
        "/incidents",
        json={
            "report_text": "Broken streetlight near City Hall",
            "location_hint": "City Hall",
        },
    ).json()

    response = client.get(f"/incidents/{created['id']}")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "id",
        "original_text",
        "language_hint",
        "detected_language",
        "issue_type",
        "severity",
        "status",
        "confidence",
        "needs_review",
        "created_at",
        "normalized_text",
        "extracted_location_text",
        "extracted_entities",
        "brief_ka",
        "brief_en",
        "failure_details",
        "updated_at",
    }
    assert body["id"] == created["id"]
    assert body["extracted_location_text"] == "City Hall"
    assert body["extracted_entities"] == {}


def test_get_missing_incident_returns_404(incident_client: tuple[TestClient, FakeIncidentSession]) -> None:
    client, _session = incident_client

    response = client.get(f"/incidents/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Incident not found"}

