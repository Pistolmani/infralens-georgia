from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

HealthStatus = Literal["ok", "degraded", "unavailable"]


class ServiceHealth(BaseModel):
    status: HealthStatus
    detail: str | None = None


class HealthResponse(BaseModel):
    status: HealthStatus
    services: dict[str, ServiceHealth]

    model_config = ConfigDict(json_schema_extra={"example": {"status": "ok", "services": {}}})

