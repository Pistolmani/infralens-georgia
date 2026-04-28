from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from app.ingestion.chunker import chunk_text
from app.ingestion.normalizer import normalize_ocds
from app.ingestion.pii import redact_pii
from app.ingestion.seed import IngestionResult, ProcurementSeedIngestor
from app.main import app
from app.models.tables import Document
from app.rag.embeddings import ConfigurationError, OllamaEmbedder
from app.workers.ingestion import ingest_procurement_seed
from app.workers.queue import get_default_queue

# ---------------------------------------------------------------------------
# Chunker tests
# ---------------------------------------------------------------------------

_LONG_TEXT = " ".join(["This is a sentence about streetlight maintenance in Tbilisi Georgia."] * 120)


def test_chunk_text_produces_correct_sizes() -> None:
    chunks = chunk_text(_LONG_TEXT, max_tokens=700, overlap_tokens=80)

    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.token_count <= 800, f"chunk {chunk.index} has {chunk.token_count} tokens"


def test_chunk_text_overlap_carries_tokens() -> None:
    chunks = chunk_text(_LONG_TEXT, max_tokens=200, overlap_tokens=40)

    assert len(chunks) >= 2
    first_end = chunks[0].text.split()[-5:]
    second_start = chunks[1].text.split()[:15]
    overlap_words = set(first_end) & set(second_start)
    assert overlap_words, "Expected some overlap words between consecutive chunks"


def test_chunk_text_single_short_document() -> None:
    short = "Streetlight on Rustaveli Avenue is broken."
    chunks = chunk_text(short)

    assert len(chunks) == 1
    assert chunks[0].text == short
    assert chunks[0].index == 0


def test_chunk_text_empty_returns_empty() -> None:
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_indexes_are_sequential() -> None:
    chunks = chunk_text(_LONG_TEXT, max_tokens=200, overlap_tokens=30)
    for i, chunk in enumerate(chunks):
        assert chunk.index == i


def test_chunk_text_long_sentence_does_not_overflow_max_tokens() -> None:
    long_sentence = "word " * 1500  # ~1500 tokens, no sentence boundary
    chunks = chunk_text(long_sentence, max_tokens=300, overlap_tokens=50)

    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.token_count <= 300, f"chunk {chunk.index} has {chunk.token_count} tokens (max=300)"


# ---------------------------------------------------------------------------
# PII redaction tests
# ---------------------------------------------------------------------------


def test_redact_pii_removes_phone_email_id() -> None:
    text = (
        "Contact: +995 32 200 1234. "
        "Email: inspector@tbilisi.gov.ge. "
        "ID: 01234567890 is the contractor ID."
    )
    redacted = redact_pii(text)

    assert "+995" not in redacted
    assert "inspector@tbilisi.gov.ge" not in redacted
    assert "01234567890" not in redacted
    assert "[PHONE]" in redacted
    assert "[EMAIL]" in redacted
    assert "[PERSONAL_ID]" in redacted


def test_redact_pii_clean_text_unchanged() -> None:
    clean = "Annual streetlight maintenance contract for Tbilisi central districts."
    assert redact_pii(clean) == clean


def test_redact_pii_preserves_non_pii_numbers() -> None:
    text = "Contract value: 2850000 GEL. Duration: 12 months. Poles: 85000."
    redacted = redact_pii(text)
    assert "2850000" in redacted
    assert "85000" in redacted


# ---------------------------------------------------------------------------
# Normalizer tests
# ---------------------------------------------------------------------------

_OCDS_FIXTURE: dict[str, Any] = {
    "ocid": "ocds-test-001",
    "buyer": {"id": "GE-TEST", "name": "Test Municipality"},
    "tender": {
        "id": "tender-001",
        "title": "LED Streetlight Replacement",
        "description": "Replace 500 sodium lamps with LED fixtures on main arterial roads.",
    },
    "awards": [{"id": "award-001", "description": "Award to lighting contractor."}],
    "contracts": [{"id": "contract-001", "description": "12-month installation contract."}],
}


def test_normalizer_extracts_ocds_fields() -> None:
    doc = normalize_ocds(_OCDS_FIXTURE, "test.json")

    assert doc.title == "LED Streetlight Replacement"
    assert doc.agency == "Test Municipality"
    assert doc.buyer == "Test Municipality"
    assert doc.procurement_id == "tender-001"
    assert doc.source_id == "ocds-test-001"
    assert "Replace 500 sodium lamps" in doc.description_text
    assert "Award to lighting contractor" in doc.description_text
    assert "12-month installation contract" in doc.description_text


def test_normalizer_falls_back_on_missing_fields() -> None:
    minimal = {"id": "fallback-001"}
    doc = normalize_ocds(minimal, "minimal.json")

    assert doc.title == "fallback-001"
    assert doc.agency is None
    assert doc.description_text == "fallback-001"


# ---------------------------------------------------------------------------
# Ingestor tests (no DB, no Ollama)
# ---------------------------------------------------------------------------


class _FakeSession:
    def __init__(self) -> None:
        self.documents: dict[str, Document] = {}
        self.chunks: list[object] = []

    def execute(self, statement: object) -> _FakeScalar:
        content_hash = _extract_hash_from_statement(statement)
        existing = next(
            (d for d in self.documents.values() if d.content_hash == content_hash),
            None,
        )
        return _FakeScalar(existing)

    def add(self, obj: object) -> None:
        if isinstance(obj, Document):
            obj.id = uuid.uuid4()
            self.documents[obj.content_hash] = obj
        else:
            self.chunks.append(obj)

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


class _FakeScalar:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


def _extract_hash_from_statement(statement: object) -> str:
    # Walk the SQLAlchemy where clause to extract the hash value for testing
    try:
        clause = statement.whereclause
        right = clause.right
        return str(right.value)
    except AttributeError:
        return ""


def _make_embedder(dimension: int = 1024) -> MagicMock:
    embedder = MagicMock(spec=OllamaEmbedder)
    embedder.embed.return_value = [0.1] * dimension
    embedder.embed_batch.side_effect = lambda texts: [[0.1] * dimension for _ in texts]
    return embedder


def test_ingestor_deduplicates_by_hash(tmp_path: Path) -> None:
    seed_file = tmp_path / "test.json"
    seed_file.write_text(json.dumps(_OCDS_FIXTURE), encoding="utf-8")

    session = _FakeSession()
    embedder = _make_embedder()
    ingestor = ProcurementSeedIngestor(db=session, embedder=embedder, seed_dir=tmp_path)

    result1 = ingestor.ingest()
    assert result1.documents_inserted == 1
    assert result1.documents_skipped == 0

    result2 = ingestor.ingest()
    assert result2.documents_inserted == 0
    assert result2.documents_skipped == 1
    # embed_batch called once per ingested document
    assert embedder.embed_batch.call_count == 1


def test_ingestor_records_error_on_bad_file(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not valid json {{{", encoding="utf-8")

    session = _FakeSession()
    embedder = _make_embedder()
    ingestor = ProcurementSeedIngestor(db=session, embedder=embedder, seed_dir=tmp_path)

    result = ingestor.ingest()

    assert len(result.errors) == 1
    assert "bad.json" in result.errors[0]
    assert result.documents_inserted == 0


def test_ingestor_continues_after_bad_file(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text("not json", encoding="utf-8")
    good_file = tmp_path / "good.json"
    good_file.write_text(json.dumps(_OCDS_FIXTURE), encoding="utf-8")

    session = _FakeSession()
    embedder = _make_embedder()
    ingestor = ProcurementSeedIngestor(db=session, embedder=embedder, seed_dir=tmp_path)

    result = ingestor.ingest()

    assert result.documents_inserted == 1
    assert len(result.errors) == 1


# ---------------------------------------------------------------------------
# Embedder dimension validation test
# ---------------------------------------------------------------------------


def _make_embedder_with_response(json_response: dict) -> OllamaEmbedder:
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = json_response

    embedder = OllamaEmbedder.__new__(OllamaEmbedder)
    embedder._base_url = "http://localhost:11434"
    embedder._model = "test-model"
    embedder._client = MagicMock()
    embedder._client.post.return_value = mock_response
    return embedder


def test_embedder_rejects_wrong_dimension() -> None:
    embedder = _make_embedder_with_response({"embeddings": [[0.1] * 512]})

    with pytest.raises(ConfigurationError, match="512"):
        embedder.embed("test text")


def test_embedder_batch_rejects_wrong_dimension() -> None:
    embedder = _make_embedder_with_response({"embeddings": [[0.1] * 1024, [0.1] * 256]})

    with pytest.raises(ConfigurationError, match="256"):
        embedder.embed_batch(["a", "b"])


def test_embedder_rejects_missing_embeddings_field() -> None:
    embedder = _make_embedder_with_response({"unexpected": "shape"})

    with pytest.raises(ConfigurationError, match="invalid"):
        embedder.embed("text")


def test_embedder_rejects_count_mismatch() -> None:
    embedder = _make_embedder_with_response({"embeddings": [[0.1] * 1024]})

    with pytest.raises(ConfigurationError, match="2 inputs"):
        embedder.embed_batch(["a", "b"])


def test_embedder_batch_empty_returns_empty() -> None:
    embedder = _make_embedder_with_response({"embeddings": []})

    assert embedder.embed_batch([]) == []


# ---------------------------------------------------------------------------
# Ingest API endpoint tests
# ---------------------------------------------------------------------------


class _FakeJob:
    id = "ingest-job-id"


class _FakeQueue:
    name = "infralens"

    def __init__(self) -> None:
        self.enqueued: list[tuple[object, tuple[object, ...]]] = []

    def enqueue(self, func: object, *args: object) -> _FakeJob:
        self.enqueued.append((func, args))
        return _FakeJob()


class _FailingQueue(_FakeQueue):
    def enqueue(self, func: object, *args: object) -> _FakeJob:
        raise RedisError("unavailable")


@pytest.fixture
def ingest_client() -> Generator[tuple[TestClient, _FakeQueue], None, None]:
    queue = _FakeQueue()
    app.dependency_overrides[get_default_queue] = lambda: queue
    with TestClient(app) as client:
        yield client, queue
    app.dependency_overrides.pop(get_default_queue, None)


def test_ingest_endpoint_requires_key(
    ingest_client: tuple[TestClient, _FakeQueue],
) -> None:
    client, _queue = ingest_client

    response = client.post("/ingest/procurement")
    assert response.status_code == 403

    response = client.post("/ingest/procurement", headers={"X-Ingest-Key": "wrong-key"})
    assert response.status_code == 403


def test_ingest_endpoint_enqueues_job(
    ingest_client: tuple[TestClient, _FakeQueue],
) -> None:
    client, queue = ingest_client

    response = client.post(
        "/ingest/procurement",
        headers={"X-Ingest-Key": "change-me-local"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == "ingest-job-id"
    assert body["queue_name"] == "infralens"
    assert body["source"] == "seed_data/procurement"
    assert queue.enqueued == [(ingest_procurement_seed, ())]


def test_ingest_endpoint_queue_failure() -> None:
    failing_queue = _FailingQueue()
    app.dependency_overrides[get_default_queue] = lambda: failing_queue
    try:
        with TestClient(app) as client:
            response = client.post(
                "/ingest/procurement",
                headers={"X-Ingest-Key": "change-me-local"},
            )
        assert response.status_code == 503
        assert response.json() == {"detail": "Ingestion queue is unavailable"}
    finally:
        app.dependency_overrides.pop(get_default_queue, None)


def test_askgov_returns_501(
    ingest_client: tuple[TestClient, _FakeQueue],
) -> None:
    client, _queue = ingest_client

    assert client.get("/ingest/askgov").status_code == 501
    assert client.post("/ingest/askgov").status_code == 501
