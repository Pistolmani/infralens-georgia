from __future__ import annotations

import httpx

from app.core.config import Settings, get_settings

EXPECTED_DIMENSIONS = 1024


class ConfigurationError(Exception):
    pass


class OllamaEmbedder:
    def __init__(self, settings: Settings | None = None) -> None:
        resolved = settings or get_settings()
        self._base_url = resolved.ollama_base_url.rstrip("/")
        self._model = resolved.ollama_embed_model
        self._client = httpx.Client(timeout=120.0)

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        response = self._client.post(
            f"{self._base_url}/api/embed",
            json={"model": self._model, "input": texts},
        )
        response.raise_for_status()
        data = response.json()

        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list) or not embeddings:
            raise ConfigurationError(
                f"Ollama embed response missing or invalid 'embeddings' field: keys={list(data.keys())}"
            )
        if len(embeddings) != len(texts):
            raise ConfigurationError(
                f"Ollama returned {len(embeddings)} vectors for {len(texts)} inputs"
            )
        for vector in embeddings:
            self._validate_dimensions(vector)
        return embeddings

    def _validate_dimensions(self, vector: list[float]) -> None:
        if len(vector) != EXPECTED_DIMENSIONS:
            raise ConfigurationError(
                f"Embedding model '{self._model}' returned {len(vector)}-dimensional vector; "
                f"expected {EXPECTED_DIMENSIONS}. "
                f"Set OLLAMA_EMBED_MODEL to a model that produces {EXPECTED_DIMENSIONS}-d embeddings (e.g. bge-m3)."
            )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OllamaEmbedder:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
