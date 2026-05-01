from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.llmops.ollama import OllamaReasoningError, ReasoningResponse
from app.llmops.prompts import Prompt, PromptRegistry
from app.llmops.tracing import AgentRunLogger
from app.schemas.agents import (
    ClassifyIncidentInput,
    ClassifyIncidentOutput,
    ExtractEntitiesInput,
    ExtractEntitiesOutput,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


class ReasoningClient(Protocol):
    model: str

    def generate_json(self, prompt: str, temperature: float) -> ReasoningResponse:
        raise NotImplementedError


class AnalysisNodeError(Exception):
    pass


@dataclass(frozen=True)
class ParsedOutput:
    output: BaseModel | None
    output_json: dict | None
    validation_errors: list[dict]


class ClassifyOnlyNodes:
    def __init__(
        self,
        *,
        client: ReasoningClient,
        prompts: PromptRegistry,
        logger: AgentRunLogger,
    ) -> None:
        self._client = client
        self._prompts = prompts
        self._logger = logger

    def extract_entities(
        self,
        *,
        incident_id: uuid.UUID,
        payload: ExtractEntitiesInput,
    ) -> ExtractEntitiesOutput:
        normalized_input = _normalize_input(payload.report_text)
        prompt = self._prompts.get("extract_entities")
        rendered = prompt.render(
            report_text=payload.report_text,
            normalized_input=normalized_input,
            language_hint=payload.language_hint or "unknown",
            location_hint=payload.location_hint or "unknown",
        )
        output = self._run_structured_node(
            incident_id=incident_id,
            node_name="ExtractEntities",
            prompt=prompt,
            rendered_prompt=rendered,
            output_model=ExtractEntitiesOutput,
            confidence_field="extract_conf",
            input_summary=_summarize_text(normalized_input),
        )
        return output

    def classify_incident(
        self,
        *,
        incident_id: uuid.UUID,
        payload: ClassifyIncidentInput,
    ) -> ClassifyIncidentOutput:
        prompt = self._prompts.get("classify_incident")
        rendered = prompt.render(
            normalized_text=payload.normalized_text,
            detected_language=payload.detected_language,
            location_text=payload.location_text or "unknown",
            entities=payload.entities.model_dump(mode="json"),
        )
        output = self._run_structured_node(
            incident_id=incident_id,
            node_name="ClassifyIncident",
            prompt=prompt,
            rendered_prompt=rendered,
            output_model=ClassifyIncidentOutput,
            confidence_field="classify_conf",
            input_summary=_summarize_text(payload.normalized_text),
        )
        return output

    def _run_structured_node(
        self,
        *,
        incident_id: uuid.UUID,
        node_name: str,
        prompt: Prompt,
        rendered_prompt: str,
        output_model: type[ModelT],
        confidence_field: str,
        input_summary: str,
    ) -> ModelT:
        started = perf_counter()
        try:
            response = self._client.generate_json(rendered_prompt, prompt.temperature)
        except OllamaReasoningError as exc:
            latency_ms = _latency_ms(started)
            self._logger.log(
                incident_id=incident_id,
                node_name=node_name,
                prompt=prompt,
                model=self._client.model,
                input_summary=input_summary,
                status="failed",
                latency_ms=latency_ms,
                validation_errors=[_issue("ollama_error", str(exc))],
            )
            raise AnalysisNodeError(f"{node_name} failed: {exc}") from exc

        parsed = _parse_output(
            response.text,
            output_model=output_model,
            confidence_field=confidence_field,
        )
        if parsed.output is not None:
            latency_ms = _latency_ms(started)
            self._logger.log(
                incident_id=incident_id,
                node_name=node_name,
                prompt=prompt,
                model=self._client.model,
                input_summary=input_summary,
                status="success",
                latency_ms=latency_ms,
                output_json=parsed.output_json,
                validation_errors=parsed.validation_errors,
                node_confidence=float(getattr(parsed.output, confidence_field)),
            )
            return parsed.output

        correction_prompt = self._prompts.get("json_correction")
        correction_rendered = correction_prompt.render(
            node_name=node_name,
            output_schema=prompt.output_schema,
            validation_errors=parsed.validation_errors,
            invalid_output=response.text,
        )
        try:
            corrected_response = self._client.generate_json(
                correction_rendered,
                correction_prompt.temperature,
            )
        except OllamaReasoningError as exc:
            latency_ms = _latency_ms(started)
            validation_errors = parsed.validation_errors + [_issue("ollama_error", str(exc))]
            self._logger.log(
                incident_id=incident_id,
                node_name=node_name,
                prompt=prompt,
                model=self._client.model,
                input_summary=input_summary,
                status="failed",
                latency_ms=latency_ms,
                output_json=parsed.output_json,
                validation_errors=validation_errors,
            )
            raise AnalysisNodeError(f"{node_name} correction failed: {exc}") from exc

        corrected = _parse_output(
            corrected_response.text,
            output_model=output_model,
            confidence_field=confidence_field,
        )
        validation_errors = parsed.validation_errors + corrected.validation_errors
        latency_ms = _latency_ms(started)
        if corrected.output is None:
            self._logger.log(
                incident_id=incident_id,
                node_name=node_name,
                prompt=prompt,
                model=self._client.model,
                input_summary=input_summary,
                status="failed",
                latency_ms=latency_ms,
                output_json=corrected.output_json,
                validation_errors=validation_errors,
            )
            raise AnalysisNodeError(f"{node_name} returned invalid JSON after correction retry")

        self._logger.log(
            incident_id=incident_id,
            node_name=node_name,
            prompt=prompt,
            model=self._client.model,
            input_summary=input_summary,
            status="success",
            latency_ms=latency_ms,
            output_json=corrected.output_json,
            validation_errors=validation_errors,
            node_confidence=float(getattr(corrected.output, confidence_field)),
        )
        return corrected.output


def _parse_output(
    text: str,
    *,
    output_model: type[ModelT],
    confidence_field: str,
) -> ParsedOutput:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        return ParsedOutput(
            output=None,
            output_json=None,
            validation_errors=[_issue("json_decode_error", str(exc))],
        )

    if not isinstance(raw, dict):
        return ParsedOutput(
            output=None,
            output_json=None,
            validation_errors=[_issue("schema_error", "Model output must be a JSON object")],
        )

    confidence_errors = _normalize_confidence(raw, confidence_field)
    try:
        output = output_model.model_validate(raw)
    except ValidationError as exc:
        return ParsedOutput(
            output=None,
            output_json=raw,
            validation_errors=confidence_errors + _pydantic_issues(exc),
        )

    return ParsedOutput(
        output=output,
        output_json=output.model_dump(mode="json"),
        validation_errors=confidence_errors,
    )


def _normalize_confidence(raw: dict, field_name: str) -> list[dict]:
    if field_name not in raw or raw[field_name] is None:
        raw[field_name] = 0.0
        return [_issue("confidence_missing", f"{field_name} was missing; defaulted to 0.0")]

    try:
        value = float(raw[field_name])
    except (TypeError, ValueError):
        raw[field_name] = 0.0
        return [_issue("confidence_invalid", f"{field_name} was invalid; defaulted to 0.0")]

    if value < 0.0 or value > 1.0:
        raw[field_name] = 0.0
        return [_issue("confidence_invalid", f"{field_name} was outside 0..1; defaulted to 0.0")]

    raw[field_name] = value
    return []


def _pydantic_issues(exc: ValidationError) -> list[dict]:
    return [
        _issue(
            "schema_validation_error",
            error["msg"],
            location=".".join(str(part) for part in error["loc"]),
        )
        for error in exc.errors()
    ]


def _issue(code: str, message: str, location: str | None = None) -> dict:
    issue = {"code": code, "message": message}
    if location:
        issue["location"] = location
    return issue


def _normalize_input(text: str) -> str:
    return " ".join(text.split())


def _summarize_text(text: str, limit: int = 300) -> str:
    normalized = _normalize_input(text)
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


def _latency_ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)
