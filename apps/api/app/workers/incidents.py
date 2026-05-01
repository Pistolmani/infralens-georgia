from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.agents.nodes import AnalysisNodeError, ClassifyOnlyNodes
from app.agents.runner import ClassifyOnlyIncidentRunner
from app.core.config import get_settings
from app.db.session import session_scope
from app.llmops.ollama import OllamaReasoningClient
from app.llmops.prompts import PromptRegistry
from app.llmops.tracing import AgentRunLogger
from app.models.tables import Incident

logger = logging.getLogger(__name__)


def analyze_incident(incident_id: str) -> None:
    with session_scope() as db:
        incident = db.get(Incident, uuid.UUID(incident_id))
        if incident is None:
            return

        incident.status = "analyzing"
        incident.failure_details = None
        incident.updated_at = datetime.now(UTC)
        db.commit()

        settings = get_settings()
        try:
            prompt_registry = PromptRegistry(settings.prompts_dir)
            run_logger = AgentRunLogger(db)
            with OllamaReasoningClient(settings) as client:
                nodes = ClassifyOnlyNodes(
                    client=client,
                    prompts=prompt_registry,
                    logger=run_logger,
                )
                result = ClassifyOnlyIncidentRunner(nodes).run(incident)

            incident.detected_language = result.extraction.detected_language
            incident.normalized_text = result.extraction.normalized_text
            incident.extracted_location_text = result.extraction.location_text
            incident.extracted_entities = result.extraction.entities.model_dump(mode="json")
            incident.issue_type = result.classification.issue_type
            incident.severity = result.classification.severity
            incident.confidence = Decimal(str(result.final_confidence))
            incident.needs_review = result.needs_review
            incident.failure_details = None
            incident.status = "analyzed"
            incident.updated_at = datetime.now(UTC)
            db.commit()
        except AnalysisNodeError as exc:
            _mark_analysis_failed(db, incident, str(exc))
        except Exception as exc:
            logger.exception("Incident analysis job failed")
            _mark_analysis_failed(db, incident, f"Unexpected analysis failure: {exc.__class__.__name__}: {exc}")
            raise


def _mark_analysis_failed(db, incident: Incident, message: str) -> None:
    incident.status = "analysis_failed"
    incident.failure_details = message
    incident.updated_at = datetime.now(UTC)
    db.commit()
