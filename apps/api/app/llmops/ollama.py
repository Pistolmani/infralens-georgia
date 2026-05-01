from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import Settings, get_settings


class OllamaReasoningError(Exception):
    pass


@dataclass(frozen=True)
class ReasoningResponse:
    text: str
    raw_response: dict


class OllamaReasoningClient:
    def __init__(
        self,
        settings: Settings | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        resolved = settings or get_settings()
        self.model = resolved.ollama_reasoning_model
        self._base_url = resolved.ollama_base_url.rstrip("/")
        self._client = http_client or httpx.Client(timeout=180.0)
        self._owns_client = http_client is None

    def generate_json(self, prompt: str, temperature: float) -> ReasoningResponse:
        try:
            response = self._client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "think": False,
                    "options": {
                        "temperature": temperature,
                        "num_ctx": 1024,
                        "num_predict": 256,
                    },
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaReasoningError(f"Ollama generate request failed: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise OllamaReasoningError("Ollama generate response was not valid JSON") from exc

        if not isinstance(data, dict):
            raise OllamaReasoningError("Ollama generate response was not a JSON object")

        text = data.get("response")
        if not isinstance(text, str):
            raise OllamaReasoningError("Ollama generate response missing string 'response' field")

        return ReasoningResponse(text=text, raw_response=data)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OllamaReasoningClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
