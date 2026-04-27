from __future__ import annotations

from app.core.config import Settings


def test_settings_defaults_match_local_runtime() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.ollama_reasoning_model == "qwen3:8b"
    assert settings.ollama_embed_model == "bge-m3"


def test_settings_support_environment_overrides(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_EMBED_MODEL", "custom-embed")
    monkeypatch.setenv("INGEST_KEY", "local-secret")

    settings = Settings(_env_file=None)

    assert settings.ollama_embed_model == "custom-embed"
    assert settings.ingest_key == "local-secret"

