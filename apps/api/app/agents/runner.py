from __future__ import annotations

from dataclasses import dataclass

from app.agents.nodes import ClassifyOnlyNodes
from app.models.tables import Incident
from app.schemas.agents import (
    ClassifyIncidentInput,
    ClassifyIncidentOutput,
    ExtractEntitiesInput,
    ExtractEntitiesOutput,
)


@dataclass(frozen=True)
class ClassifyOnlyAnalysisResult:
    extraction: ExtractEntitiesOutput
    classification: ClassifyIncidentOutput
    final_confidence: float
    needs_review: bool


class ClassifyOnlyIncidentRunner:
    def __init__(self, nodes: ClassifyOnlyNodes) -> None:
        self._nodes = nodes

    def run(self, incident: Incident) -> ClassifyOnlyAnalysisResult:
        extraction = self._nodes.extract_entities(
            incident_id=incident.id,
            payload=ExtractEntitiesInput(
                report_text=incident.original_text,
                language_hint=incident.language_hint,
                location_hint=incident.extracted_location_text,
            ),
        )
        classification = self._nodes.classify_incident(
            incident_id=incident.id,
            payload=ClassifyIncidentInput(
                normalized_text=extraction.normalized_text,
                detected_language=extraction.detected_language,
                location_text=extraction.location_text,
                entities=extraction.entities,
            ),
        )
        final_confidence = min(extraction.extract_conf, classification.classify_conf)
        return ClassifyOnlyAnalysisResult(
            extraction=extraction,
            classification=classification,
            final_confidence=final_confidence,
            needs_review=final_confidence == 0.0,
        )
