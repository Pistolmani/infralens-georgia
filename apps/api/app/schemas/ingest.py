from __future__ import annotations

from pydantic import BaseModel


class IngestionEnqueueResponse(BaseModel):
    job_id: str
    queue_name: str
    source: str
