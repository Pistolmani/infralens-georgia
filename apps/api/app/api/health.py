from __future__ import annotations

from fastapi import APIRouter

from app.core.health import get_health_snapshot
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return get_health_snapshot()

