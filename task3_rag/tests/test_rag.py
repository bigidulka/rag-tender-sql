"""Тесты сервиса на локальном бэкенде — без ключей и без сети."""

from __future__ import annotations

import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.chunking import split_document  # noqa: E402
from app.main import app  # noqa: E402

SAMPLE = pathlib.Path(__file__).resolve().parents[1] / "sample" / "regulation.txt"


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_chunks_overlap_and_fit_limit() -> None:
    text = SAMPLE.read_text(encoding="utf-8")
    chunks = split_document(text, chunk_size=400, overlap=80)
    assert len(chunks) > 1
    assert all(len(chunk.text) <= 400 + 80 for chunk in chunks)
    assert [chunk.id for chunk in chunks] == list(range(len(chunks)))


def test_overlap_must_be_smaller_than_chunk() -> None:
    with pytest.raises(ValueError):
        split_document("текст", chunk_size=100, overlap=100)


def test_ask_before_upload_returns_409(client: TestClient) -> None:
    assert client.post("/ask", json={"question": "когда релизы?"}).status_code == 409


def test_upload_and_ask_finds_relevant_chunk(client: TestClient) -> None:
    with SAMPLE.open("rb") as handle:
        ingest = client.post("/documents", files={"file": ("regulation.txt", handle, "text/plain")})
    assert ingest.status_code == 200
    assert ingest.json()["chunks"] > 3

    answer = client.post("/ask", json={"question": "Сколько дней отпуска и за сколько подавать заявку?"})
    assert answer.status_code == 200
    payload = answer.json()
    assert payload["citations"], "поиск обязан вернуть хотя бы один фрагмент"
    joined = " ".join(citation["text"] for citation in payload["citations"])
    assert "28 календарных дней" in joined


def test_release_window_question(client: TestClient) -> None:
    with SAMPLE.open("rb") as handle:
        client.post("/documents", files={"file": ("regulation.txt", handle, "text/plain")})
    payload = client.post("/ask", json={"question": "В какие дни выкатывают релизы в прод?"}).json()
    joined = " ".join(citation["text"] for citation in payload["citations"])
    assert "понедельника по четверг" in joined


def test_health_reports_backends(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["embedding_backend"] in {"local", "openai"}
    assert body["vector_backend"] in {"faiss", "numpy"}
