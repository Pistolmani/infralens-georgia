from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


DetectedLanguage = Literal["ka", "en", "ru", "unknown"]


class ExtractedEntities(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    street_names: list[str] = Field(default_factory=list)
    agencies: list[str] = Field(default_factory=list)
    procurement_terms: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    infrastructure_objects: list[str] = Field(default_factory=list)
    other: list[str] = Field(default_factory=list)


class ExtractEntitiesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    report_text: str = Field(min_length=1)
    language_hint: Literal["ka", "en"] | None = None
    location_hint: str | None = None


class ExtractEntitiesOutput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    normalized_text: str = Field(min_length=1)
    detected_language: DetectedLanguage
    location_text: str | None = None
    entities: ExtractedEntities
    extract_conf: float = Field(ge=0.0, le=1.0)

    @field_validator("location_text", mode="before")
    @classmethod
    def empty_location_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value


class ClassifyIncidentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    normalized_text: str = Field(min_length=1)
    detected_language: DetectedLanguage
    location_text: str | None = None
    entities: ExtractedEntities = Field(default_factory=ExtractedEntities)


class ClassifyIncidentOutput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    issue_type: str = Field(min_length=1)
    severity: Literal["low", "medium", "high"]
    rationale: str = Field(min_length=1)
    classify_conf: float = Field(ge=0.0, le=1.0)

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower().replace(" ", "_")
        return value

    @field_validator("issue_type", mode="after")
    @classmethod
    def normalize_issue_type(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "_")
