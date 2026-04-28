from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from rq import Queue

from app.core.config import Settings, get_settings
from app.ingestion.constants import PROCUREMENT_SOURCE_LABEL
from app.schemas.ingest import IngestionEnqueueResponse
from app.workers.ingestion import ingest_procurement_seed
from app.workers.queue import enqueue_or_503, get_default_queue

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post(
    "/procurement",
    response_model=IngestionEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_procurement_ingest(
    settings: Annotated[Settings, Depends(get_settings)],
    queue: Annotated[Queue, Depends(get_default_queue)],
    x_ingest_key: Annotated[str | None, Header()] = None,
) -> IngestionEnqueueResponse:
    if x_ingest_key != settings.ingest_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing ingest key",
        )

    job = enqueue_or_503(
        queue,
        ingest_procurement_seed,
        detail="Ingestion queue is unavailable",
    )

    return IngestionEnqueueResponse(
        job_id=job.id,
        queue_name=queue.name,
        source=PROCUREMENT_SOURCE_LABEL,
    )


@router.get("/askgov", status_code=status.HTTP_501_NOT_IMPLEMENTED)
@router.post("/askgov", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def askgov_not_implemented() -> dict[str, str]:
    return {"detail": "Askgov ingestion is not implemented in v1"}
