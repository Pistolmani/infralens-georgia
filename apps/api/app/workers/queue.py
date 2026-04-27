from __future__ import annotations

from redis import Redis
from rq import Queue

from app.core.config import Settings, get_settings

DEFAULT_QUEUE_NAME = "infralens"


def get_queue(settings: Settings | None = None, name: str = DEFAULT_QUEUE_NAME) -> Queue:
    resolved_settings = settings or get_settings()
    connection = Redis.from_url(resolved_settings.redis_url)
    return Queue(name, connection=connection)

