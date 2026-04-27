from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IncidentStatus(str, Enum):
    created = "created"
    queued = "queued"
    analyzing = "analyzing"
    analyzed = "analyzed"
    analysis_failed = "analysis_failed"


class IncidentCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    report_text: str = Field(min_length=1, max_length=10_000)
    language_hint: str | None = Field(default=None, pattern="^(ka|en)$")
    location_hint: str | None = Field(default=None, max_length=500)

    @field_validator("language_hint", mode="before")
    @classmethod
    def normalize_language_hint(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized or None
        return value

    @field_validator("location_hint", mode="before")
    @classmethod
    def normalize_location_hint(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value


class IncidentSummaryResponse(BaseModel):
    id: uuid.UUID
    original_text: str
    language_hint: str | None
    detected_language: str | None
    issue_type: str | None
    severity: str | None
    status: IncidentStatus
    confidence: Decimal | None
    needs_review: bool
    created_at: datetime


class IncidentDetailResponse(IncidentSummaryResponse):
    normalized_text: str | None
    extracted_location_text: str | None
    extracted_entities: dict
    brief_ka: str | None
    brief_en: str | None
    failure_details: str | None
    updated_at: datetime


class IncidentListResponse(BaseModel):
    items: list[IncidentSummaryResponse]
    limit: int
    offset: int

