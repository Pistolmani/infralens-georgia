from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.exceptions import RedisError
from rq import Queue
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.tables import Incident
from app.schemas.incidents import (
    IncidentAnalyzeResponse,
    IncidentCreateRequest,
    IncidentDetailResponse,
    IncidentListResponse,
    IncidentSummaryResponse,
)
from app.workers.incidents import analyze_incident
from app.workers.queue import get_default_queue

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _incident_summary(incident: Incident) -> IncidentSummaryResponse:
    return IncidentSummaryResponse(
        id=incident.id,
        original_text=incident.original_text,
        language_hint=incident.language_hint,
        detected_language=incident.detected_language,
        issue_type=incident.issue_type,
        severity=incident.severity,
        status=incident.status,
        confidence=incident.confidence,
        needs_review=incident.needs_review,
        created_at=incident.created_at,
    )


def _incident_detail(incident: Incident) -> IncidentDetailResponse:
    return IncidentDetailResponse(
        **_incident_summary(incident).model_dump(),
        normalized_text=incident.normalized_text,
        extracted_location_text=incident.extracted_location_text,
        extracted_entities=incident.extracted_entities,
        brief_ka=incident.brief_ka,
        brief_en=incident.brief_en,
        failure_details=incident.failure_details,
        updated_at=incident.updated_at,
    )


@router.post(
    "",
    response_model=IncidentSummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_incident(payload: IncidentCreateRequest, db: Annotated[Session, Depends(get_db)]) -> IncidentSummaryResponse:
    incident = Incident(
        original_text=payload.report_text,
        language_hint=payload.language_hint,
        extracted_location_text=payload.location_hint,
        extracted_entities={},
        status="created",
        needs_review=False,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)

    return _incident_summary(incident)


@router.get("", response_model=IncidentListResponse)
def list_incidents(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> IncidentListResponse:
    statement = select(Incident).order_by(Incident.created_at.desc()).offset(offset).limit(limit)
    incidents = db.execute(statement).scalars().all()

    return IncidentListResponse(
        items=[_incident_summary(incident) for incident in incidents],
        limit=limit,
        offset=offset,
    )


@router.get("/{incident_id}", response_model=IncidentDetailResponse)
def get_incident(incident_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> IncidentDetailResponse:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )

    return _incident_detail(incident)


@router.post(
    "/{incident_id}/analyze",
    response_model=IncidentAnalyzeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def analyze_incident_endpoint(
    incident_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    queue: Annotated[Queue, Depends(get_default_queue)],
) -> IncidentAnalyzeResponse:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )

    previous_status = incident.status
    previous_failure_details = incident.failure_details
    previous_updated_at = incident.updated_at

    incident.status = "queued"
    incident.failure_details = None
    incident.updated_at = datetime.now(UTC)

    try:
        job = queue.enqueue(analyze_incident, str(incident.id))
    except RedisError as exc:
        incident.status = previous_status
        incident.failure_details = previous_failure_details
        incident.updated_at = previous_updated_at
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analysis queue is unavailable",
        ) from exc

    db.commit()
    db.refresh(incident)

    return IncidentAnalyzeResponse(
        incident_id=incident.id,
        status=incident.status,
        job_id=job.id,
        queue_name=queue.name,
    )
