from __future__ import annotations

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="InfraLens Georgia local-first incident analysis API.",
)
app.include_router(health_router)

