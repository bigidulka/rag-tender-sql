"""FastAPI-сервис: загрузка документа, поиск по базе знаний, ответ по контексту.

Эндпоинты:
    POST /documents      — загрузить .txt/.md (form-data, поле file) или JSON {"text": ...}
    POST /ask            — {"question": "..."} → ответ + процитированные фрагменты
    GET  /health         — состояние индекса и выбранных бэкендов

Хранилище держится в памяти процесса: задание — мини-сервис на один документ,
а не многопользовательская база. Точка расширения одна — VectorStore, за ним
уже стоит FAISS.
"""

from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .chunking import split_document
from .config import settings
from .embeddings import build_embedder
from .llm import answer
from .store import VectorStore

app = FastAPI(title="Knowledge base RAG", version="1.0.0")

_embedder = build_embedder()
_store = VectorStore(dim=_embedder.dim)
_document_name: str | None = None


class IngestBody(BaseModel):
    text: str = Field(min_length=1)
    name: str = "inline"


class IngestResult(BaseModel):
    document: str
    chunks: int
    embedding_backend: str
    vector_backend: str


class AskBody(BaseModel):
    question: str = Field(min_length=3)
    top_k: int | None = None


class Citation(BaseModel):
    chunk_id: int
    score: float
    text: str


class AskResult(BaseModel):
    answer: str
    generation_backend: str
    citations: list[Citation]


def _ingest(text: str, name: str) -> IngestResult:
    global _document_name, _store

    chunks = split_document(text, settings.chunk_size, settings.chunk_overlap)
    if not chunks:
        raise HTTPException(status_code=400, detail="документ пустой")

    # Перезагрузка документа заменяет базу целиком: иначе ответы начинают
    # смешивать редакции регламента, и понять, какая из них процитирована,
    # уже нельзя.
    _store = VectorStore(dim=_embedder.dim)
    _store.add(chunks, _embedder.embed([chunk.text for chunk in chunks]))
    _document_name = name
    return IngestResult(
        document=name,
        chunks=len(chunks),
        embedding_backend=settings.embedding_backend,
        vector_backend=_store.backend,
    )


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "document": _document_name,
        "chunks": len(_store),
        "embedding_backend": settings.embedding_backend,
        "generation_backend": settings.generation_backend,
        "vector_backend": _store.backend,
    }


@app.post("/documents", response_model=IngestResult)
async def upload_document(file: UploadFile = File(...)) -> IngestResult:
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="ожидается текст в UTF-8") from exc
    return _ingest(text, file.filename or "upload.txt")


@app.post("/documents/text", response_model=IngestResult)
def upload_text(body: IngestBody) -> IngestResult:
    return _ingest(body.text, body.name)


@app.post("/ask", response_model=AskResult)
def ask(body: AskBody) -> AskResult:
    if not len(_store):
        raise HTTPException(status_code=409, detail="сначала загрузите документ")

    vector = _embedder.embed([body.question])[0]
    hits = _store.search(vector, body.top_k or settings.top_k)
    text, backend = answer(body.question, hits)
    return AskResult(
        answer=text,
        generation_backend=backend,
        citations=[
            Citation(chunk_id=hit.chunk.id, score=round(hit.score, 4), text=hit.chunk.text)
            for hit in hits
        ],
    )
