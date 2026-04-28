from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from redis import Redis
from redis.exceptions import RedisError
from rq import Queue
from rq.job import Job

from app.core.config import Settings, get_settings

DEFAULT_QUEUE_NAME = "infralens"


def get_queue(settings: Settings | None = None, name: str = DEFAULT_QUEUE_NAME) -> Queue:
    resolved_settings = settings or get_settings()
    connection = Redis.from_url(resolved_settings.redis_url)
    return Queue(name, connection=connection)


def get_default_queue() -> Queue:
    return get_queue()


def enqueue_or_503(queue: Queue, func: Any, *args: Any, detail: str) -> Job:
    try:
        return queue.enqueue(func, *args)
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        ) from exc
