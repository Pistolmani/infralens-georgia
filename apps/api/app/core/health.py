from __future__ import annotations

import httpx
import redis
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings
from app.schemas.health import HealthResponse, ServiceHealth


def check_database(settings: Settings) -> ServiceHealth:
    try:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
    except SQLAlchemyError as exc:
        return ServiceHealth(status="unavailable", detail=exc.__class__.__name__)
    return ServiceHealth(status="ok")


def check_redis(settings: Settings) -> ServiceHealth:
    try:
        client = redis.Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
    except redis.RedisError as exc:
        return ServiceHealth(status="degraded", detail=exc.__class__.__name__)
    return ServiceHealth(status="ok")


def check_ollama(settings: Settings) -> ServiceHealth:
    try:
        with httpx.Client(timeout=1.5) as client:
            response = client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
            response.raise_for_status()
    except (httpx.HTTPError, OSError) as exc:
        return ServiceHealth(status="degraded", detail=exc.__class__.__name__)
    return ServiceHealth(status="ok")


def get_health_snapshot(settings: Settings | None = None) -> HealthResponse:
    resolved_settings = settings or get_settings()
    services = {
        "database": check_database(resolved_settings),
        "redis": check_redis(resolved_settings),
        "ollama": check_ollama(resolved_settings),
    }

    if services["database"].status == "unavailable":
        status = "unavailable"
    elif any(service.status != "ok" for service in services.values()):
        status = "degraded"
    else:
        status = "ok"

    return HealthResponse(status=status, services=services)

