from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.core.config import Settings
from app.llmops.ollama import OllamaReasoningClient, OllamaReasoningError
from app.llmops.prompts import PromptRegistry, PromptRegistryError


def _write_prompt(path: Path, *, name: str = "extract_entities", omit_template: bool = False) -> None:
    template = "" if omit_template else "\ntemplate: |\n  Report: $report_text\n"
    path.write_text(
        "\n".join(
            [
                f"name: {name}",
                "version: v1",
                "model: qwen3:8b",
                "temperature: 0.0",
                "output_schema: ExtractEntitiesOutput",
            ]
        )
        + template,
        encoding="utf-8",
    )


def test_prompt_registry_loads_required_yaml_fields(tmp_path: Path) -> None:
    _write_prompt(tmp_path / "extract_entities.yaml")

    registry = PromptRegistry(tmp_path)
    prompt = registry.get("extract_entities")

    assert prompt.name == "extract_entities"
    assert prompt.version == "v1"
    assert prompt.temperature == 0.0
    assert prompt.render(report_text="Streetlight outage") == "Report: Streetlight outage\n"


def test_prompt_registry_rejects_missing_required_fields(tmp_path: Path) -> None:
    _write_prompt(tmp_path / "extract_entities.yaml", omit_template=True)

    with pytest.raises(PromptRegistryError, match="missing required"):
        PromptRegistry(tmp_path)


class FakeResponse:
    def __init__(self, body: object) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._body


class FakeHttpClient:
    def __init__(self, response: object | Exception) -> None:
        self.response = response
        self.requests: list[dict] = []
        self.closed = False

    def post(self, url: str, json: dict) -> FakeResponse:
        self.requests.append({"url": url, "json": json})
        if isinstance(self.response, Exception):
            raise self.response
        return FakeResponse(self.response)

    def close(self) -> None:
        self.closed = True


def test_ollama_reasoning_client_parses_generate_response() -> None:
    http_client = FakeHttpClient({"response": "{\"ok\": true}"})
    settings = Settings(_env_file=None, OLLAMA_REASONING_MODEL="test-model")
    client = OllamaReasoningClient(settings=settings, http_client=http_client)

    response = client.generate_json("Return JSON", temperature=0.0)

    assert response.text == "{\"ok\": true}"
    assert http_client.requests[0]["json"] == {
        "model": "test-model",
        "prompt": "Return JSON",
        "stream": False,
        "format": "json",
        "think": False,
        "options": {
            "temperature": 0.0,
            "num_ctx": 1024,
            "num_predict": 256,
        },
    }


def test_ollama_reasoning_client_wraps_network_errors() -> None:
    http_client = FakeHttpClient(httpx.TimeoutException("timed out"))
    client = OllamaReasoningClient(settings=Settings(_env_file=None), http_client=http_client)

    with pytest.raises(OllamaReasoningError, match="request failed"):
        client.generate_json("Return JSON", temperature=0.0)


def test_ollama_reasoning_client_rejects_malformed_response() -> None:
    http_client = FakeHttpClient({"done": True})
    client = OllamaReasoningClient(settings=Settings(_env_file=None), http_client=http_client)

    with pytest.raises(OllamaReasoningError, match="missing string 'response'"):
        client.generate_json("Return JSON", temperature=0.0)
