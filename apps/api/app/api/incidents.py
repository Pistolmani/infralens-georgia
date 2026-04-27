from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.tables import Incident
from app.schemas.incidents import (
    IncidentCreateRequest,
    IncidentDetailResponse,
    IncidentListResponse,
    IncidentSummaryResponse,
)

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

