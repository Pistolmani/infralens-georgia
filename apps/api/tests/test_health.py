from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.health import get_health_snapshot
from app.main import app
from app.schemas.health import HealthResponse, ServiceHealth


def test_healthz_returns_structured_response(monkeypatch) -> None:
    def fake_health_snapshot() -> HealthResponse:
        return HealthResponse(
            status="degraded",
            services={
                "database": ServiceHealth(status="ok"),
                "redis": ServiceHealth(status="ok"),
                "ollama": ServiceHealth(status="degraded", detail="ConnectError"),
            },
        )

    monkeypatch.setattr("app.api.health.get_health_snapshot", fake_health_snapshot)

    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "services": {
            "database": {"status": "ok", "detail": None},
            "redis": {"status": "ok", "detail": None},
            "ollama": {"status": "degraded", "detail": "ConnectError"},
        },
    }


def test_health_snapshot_marks_database_unavailable(monkeypatch) -> None:
    settings = Settings(_env_file=None)

    monkeypatch.setattr("app.core.health.check_database", lambda _: ServiceHealth(status="unavailable"))
    monkeypatch.setattr("app.core.health.check_redis", lambda _: ServiceHealth(status="ok"))
    monkeypatch.setattr("app.core.health.check_ollama", lambda _: ServiceHealth(status="ok"))

    snapshot = get_health_snapshot(settings)

    assert snapshot.status == "unavailable"
    assert snapshot.services["database"].status == "unavailable"

