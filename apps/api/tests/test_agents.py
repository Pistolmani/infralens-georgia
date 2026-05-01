from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.agents.nodes import AnalysisNodeError, ClassifyOnlyNodes
from app.agents.runner import ClassifyOnlyIncidentRunner
from app.llmops.ollama import OllamaReasoningError, ReasoningResponse
from app.llmops.prompts import PromptRegistry
from app.models.tables import Incident
from app.schemas.agents import ClassifyIncidentInput, ExtractedEntities, ExtractEntitiesInput


class FakeReasoningClient:
    model = "fake-model"

    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, float]] = []

    def generate_json(self, prompt: str, temperature: float) -> ReasoningResponse:
        self.calls.append((prompt, temperature))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return ReasoningResponse(text=response, raw_response={})


class FakeAgentRunLogger:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def log(self, **kwargs: object) -> None:
        self.rows.append(kwargs)


def _prompt_dir(tmp_path: Path) -> Path:
    (tmp_path / "extract_entities.yaml").write_text(
        """
name: extract_entities
version: v1
model: qwen3:8b
temperature: 0.0
output_schema: ExtractEntitiesOutput
template: |
  Extract from: $normalized_input
""",
        encoding="utf-8",
    )
    (tmp_path / "classify_incident.yaml").write_text(
        """
name: classify_incident
version: v1
model: qwen3:8b
temperature: 0.0
output_schema: ClassifyIncidentOutput
template: |
  Classify: $normalized_text
  Entities: $entities
""",
        encoding="utf-8",
    )
    (tmp_path / "json_correction.yaml").write_text(
        """
name: json_correction
version: v1
model: qwen3:8b
temperature: 0.0
output_schema: CorrectedJson
template: |
  Correct $node_name: $validation_errors $invalid_output
""",
        encoding="utf-8",
    )
    return tmp_path


def _nodes(tmp_path: Path, client: FakeReasoningClient, logger: FakeAgentRunLogger) -> ClassifyOnlyNodes:
    return ClassifyOnlyNodes(
        client=client,
        prompts=PromptRegistry(_prompt_dir(tmp_path)),
        logger=logger,
    )


def _extract_response(confidence_field: str = '"extract_conf": 0.91') -> str:
    return f"""
    {{
      "normalized_text": "Streetlight outage near Rustaveli Avenue",
      "detected_language": "en",
      "location_text": "Rustaveli Avenue",
      "entities": {{
        "street_names": ["Rustaveli Avenue"],
        "agencies": [],
        "procurement_terms": [],
        "dates": [],
        "infrastructure_objects": ["streetlight"],
        "other": []
      }},
      {confidence_field}
    }}
    """


def _classify_response(
    confidence_field: str = '"classify_conf": 0.82',
    severity: str = "medium",
) -> str:
    return f"""
    {{
      "issue_type": "streetlight",
      "severity": "{severity}",
      "rationale": "The report describes a public lighting outage.",
      {confidence_field}
    }}
    """


def test_extract_entities_normalizes_input_inside_node(tmp_path: Path) -> None:
    client = FakeReasoningClient([_extract_response()])
    logger = FakeAgentRunLogger()
    nodes = _nodes(tmp_path, client, logger)

    output = nodes.extract_entities(
        incident_id=uuid.uuid4(),
        payload=ExtractEntitiesInput(
            report_text="  Streetlight   outage\nnear Rustaveli Avenue  ",
            language_hint="en",
            location_hint=None,
        ),
    )

    assert "Extract from: Streetlight outage near Rustaveli Avenue" in client.calls[0][0]
    assert output.entities.street_names == ["Rustaveli Avenue"]
    assert logger.rows[0]["status"] == "success"
    assert logger.rows[0]["validation_errors"] == []


def test_classify_incident_produces_streetlight_result(tmp_path: Path) -> None:
    client = FakeReasoningClient([_classify_response(severity="Medium")])
    logger = FakeAgentRunLogger()
    nodes = _nodes(tmp_path, client, logger)

    output = nodes.classify_incident(
        incident_id=uuid.uuid4(),
        payload=ClassifyIncidentInput(
            normalized_text="Streetlight outage near Rustaveli Avenue",
            detected_language="en",
            entities=ExtractedEntities(infrastructure_objects=["streetlight"]),
        ),
    )

    assert output.issue_type == "streetlight"
    assert output.severity == "medium"
    assert output.classify_conf == 0.82
    assert logger.rows[0]["node_confidence"] == 0.82


def test_extract_entities_accepts_russian_detected_language(tmp_path: Path) -> None:
    client = FakeReasoningClient([_extract_response().replace('"detected_language": "en"', '"detected_language": "ru"')])
    logger = FakeAgentRunLogger()
    nodes = _nodes(tmp_path, client, logger)

    output = nodes.extract_entities(
        incident_id=uuid.uuid4(),
        payload=ExtractEntitiesInput(report_text="Не работает уличное освещение"),
    )

    assert output.detected_language == "ru"
    assert logger.rows[0]["status"] == "success"


def test_invalid_severity_triggers_correction_retry(tmp_path: Path) -> None:
    client = FakeReasoningClient(
        [
            _classify_response(severity="banana"),
            _classify_response(severity="high"),
        ]
    )
    logger = FakeAgentRunLogger()
    nodes = _nodes(tmp_path, client, logger)

    output = nodes.classify_incident(
        incident_id=uuid.uuid4(),
        payload=ClassifyIncidentInput(
            normalized_text="Streetlight outage near Rustaveli Avenue",
            detected_language="en",
            entities=ExtractedEntities(infrastructure_objects=["streetlight"]),
        ),
    )

    assert output.severity == "high"
    assert len(client.calls) == 2
    assert logger.rows[0]["status"] == "success"
    assert logger.rows[0]["validation_errors"][0]["code"] == "schema_validation_error"


def test_node_retries_once_after_invalid_json(tmp_path: Path) -> None:
    client = FakeReasoningClient(["not json", _extract_response()])
    logger = FakeAgentRunLogger()
    nodes = _nodes(tmp_path, client, logger)

    output = nodes.extract_entities(
        incident_id=uuid.uuid4(),
        payload=ExtractEntitiesInput(report_text="Streetlight outage"),
    )

    assert output.extract_conf == 0.91
    assert len(client.calls) == 2
    assert logger.rows[0]["status"] == "success"
    assert logger.rows[0]["validation_errors"][0]["code"] == "json_decode_error"


def test_node_logs_failure_after_repeated_invalid_json(tmp_path: Path) -> None:
    client = FakeReasoningClient(["not json", "still not json"])
    logger = FakeAgentRunLogger()
    nodes = _nodes(tmp_path, client, logger)

    with pytest.raises(AnalysisNodeError, match="invalid JSON after correction retry"):
        nodes.extract_entities(
            incident_id=uuid.uuid4(),
            payload=ExtractEntitiesInput(report_text="Streetlight outage"),
        )

    assert len(client.calls) == 2
    assert logger.rows[0]["status"] == "failed"
    assert [error["code"] for error in logger.rows[0]["validation_errors"]] == [
        "json_decode_error",
        "json_decode_error",
    ]


def test_node_logs_ollama_network_failure_without_retry(tmp_path: Path) -> None:
    client = FakeReasoningClient([OllamaReasoningError("timed out")])
    logger = FakeAgentRunLogger()
    nodes = _nodes(tmp_path, client, logger)

    with pytest.raises(AnalysisNodeError, match="timed out"):
        nodes.extract_entities(
            incident_id=uuid.uuid4(),
            payload=ExtractEntitiesInput(report_text="Streetlight outage"),
        )

    assert len(client.calls) == 1
    assert logger.rows[0]["status"] == "failed"
    assert logger.rows[0]["validation_errors"][0]["code"] == "ollama_error"


def test_missing_confidence_forces_final_confidence_to_zero(tmp_path: Path) -> None:
    incident = Incident(
        id=uuid.uuid4(),
        original_text="Streetlight outage near Rustaveli Avenue",
        extracted_entities={},
        status="queued",
        needs_review=False,
    )
    client = FakeReasoningClient(
        [
            _extract_response(confidence_field='"extract_conf": null'),
            _classify_response(),
        ]
    )
    logger = FakeAgentRunLogger()
    runner = ClassifyOnlyIncidentRunner(_nodes(tmp_path, client, logger))

    result = runner.run(incident)

    assert result.extraction.extract_conf == 0.0
    assert result.classification.classify_conf == 0.82
    assert result.final_confidence == 0.0
    assert result.needs_review is True
    assert logger.rows[0]["validation_errors"][0]["code"] == "confidence_missing"
