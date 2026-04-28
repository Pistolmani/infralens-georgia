from __future__ import annotations

import uuid
from collections.abc import Generator
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.search import get_embedder
from app.db.session import get_db
from app.main import app
from app.rag.embeddings import OllamaEmbedder
from app.rag.retrieval import RetrievalResult


def _make_result(chunk_id: uuid.UUID, doc_id: uuid.UUID, rank: int, source: str) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id=doc_id,
        rank=rank,
        score=1.0 / rank,
        chunk_text=f"Streetlight maintenance content for chunk {rank}",
        chunk_metadata={"title": f"Doc {rank}"},
        source=source,  # type: ignore[arg-type]
    )


@pytest.fixture
def search_client() -> Generator[tuple[TestClient, MagicMock, MagicMock], None, None]:
    embedder = MagicMock(spec=OllamaEmbedder)
    embedder.embed.return_value = [0.1] * 1024

    db = MagicMock()

    def override_get_db() -> Generator[MagicMock, None, None]:
        yield db

    def override_get_embedder() -> MagicMock:
        return embedder

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_embedder] = override_get_embedder
    with TestClient(app) as client:
        yield client, db, embedder
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_embedder, None)


def test_search_requires_non_empty_query(
    search_client: tuple[TestClient, MagicMock, MagicMock],
) -> None:
    client, _db, _embedder = search_client

    response = client.get("/search?q=")
    assert response.status_code == 422


def test_search_returns_top5_with_confidence(
    search_client: tuple[TestClient, MagicMock, MagicMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _db, _embedder = search_client

    chunk_ids = [uuid.uuid4() for _ in range(5)]
    doc_id = uuid.uuid4()
    vector_results = [_make_result(c, doc_id, rank=i + 1, source="vector") for i, c in enumerate(chunk_ids)]
    text_results = [_make_result(chunk_ids[0], doc_id, rank=1, source="text")]

    def fake_retrieve(self, query: str, limit_per_retriever: int = 20):
        return vector_results, text_results

    monkeypatch.setattr("app.api.search.HybridRetriever.retrieve", fake_retrieve)

    response = client.get("/search?q=streetlight rustaveli")

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "streetlight rustaveli"
    assert len(body["results"]) == 5
    assert body["results"][0]["chunk_id"] == str(chunk_ids[0])
    assert body["results"][0]["rank_per_retriever"] == {"vector": 1, "text": 1}
    assert body["retrieval_confidence"] > 0


def test_search_handles_embedder_failure(
    search_client: tuple[TestClient, MagicMock, MagicMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _db, _embedder = search_client

    def fake_retrieve(self, query: str, limit_per_retriever: int = 20):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.api.search.HybridRetriever.retrieve", fake_retrieve)

    response = client.get("/search?q=test")
    assert response.status_code == 503
    assert "Retrieval unavailable" in response.json()["detail"]


def test_search_empty_results_returns_zero_confidence(
    search_client: tuple[TestClient, MagicMock, MagicMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _db, _embedder = search_client

    def fake_retrieve(self, query: str, limit_per_retriever: int = 20):
        return [], []

    monkeypatch.setattr("app.api.search.HybridRetriever.retrieve", fake_retrieve)

    response = client.get("/search?q=zzzzz no matches zzzzz")
    assert response.status_code == 200
    body = response.json()
    assert body["results"] == []
    assert body["retrieval_confidence"] == 0.0


def test_search_clamps_limit_to_5(
    search_client: tuple[TestClient, MagicMock, MagicMock],
) -> None:
    client, _db, _embedder = search_client

    response = client.get("/search?q=test&limit=20")
    assert response.status_code == 422
