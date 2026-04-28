from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "InfraLens Georgia"
    environment: str = Field(default="development", alias="ENVIRONMENT")
    database_url: str = Field(
        default="postgresql+psycopg://infralens:infralens@localhost:5432/infralens",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_reasoning_model: str = Field(default="qwen3:8b", alias="OLLAMA_REASONING_MODEL")
    ollama_embed_model: str = Field(default="bge-m3", alias="OLLAMA_EMBED_MODEL")
    ingest_key: str = Field(default="change-me-local", alias="INGEST_KEY")
    seed_data_dir: Path = Field(default=Path("seed_data/procurement"), alias="SEED_DATA_DIR")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

