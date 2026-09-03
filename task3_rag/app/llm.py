"""Генерация ответа по найденному контексту.

Провайдер выбирается по наличию ключа: Anthropic → OpenAI → Ollama → extractive.
Extractive — не «заглушка ради зелёного теста», а осознанный фолбэк: он
возвращает те же найденные фрагменты без перефразирования, поэтому сервис
остаётся полезным и проверяемым без единого ключа, а ответ никогда не
выдумывается.
"""

from __future__ import annotations

import httpx

from .config import settings
from .store import SearchHit

SYSTEM_PROMPT = (
    "Ты отвечаешь на вопросы строго по приведённым фрагментам документа. "
    "Если ответа во фрагментах нет — так и скажи. Не добавляй фактов от себя. "
    "В конце ответа перечисли номера использованных фрагментов."
)


def build_context(hits: list[SearchHit], limit: int) -> str:
    parts: list[str] = []
    used = 0
    for hit in hits:
        block = f"[фрагмент {hit.chunk.id}]\n{hit.chunk.text}"
        if used + len(block) > limit:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


def _extractive(question: str, hits: list[SearchHit]) -> str:
    if not hits:
        return "В загруженном документе ничего похожего не нашлось."
    best = hits[0]
    others = ", ".join(str(h.chunk.id) for h in hits[1:])
    tail = f" Смежные фрагменты: {others}." if others else ""
    return (
        f"Ответ по документу (фрагмент {best.chunk.id}):\n\n{best.chunk.text}\n\n"
        f"Вопрос: {question}.{tail}"
    )


def _anthropic(question: str, context: str) -> str:
    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": settings.anthropic_key or "",
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": "claude-sonnet-4-5",
            "max_tokens": 800,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": f"Фрагменты:\n{context}\n\nВопрос: {question}"}
            ],
        },
        timeout=settings.request_timeout,
    )
    response.raise_for_status()
    return "".join(
        block.get("text", "") for block in response.json().get("content", [])
    ).strip()


def _openai(question: str, context: str) -> str:
    response = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.openai_key}"},
        json={
            "model": "gpt-4o-mini",
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Фрагменты:\n{context}\n\nВопрос: {question}"},
            ],
        },
        timeout=settings.request_timeout,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def _ollama(question: str, context: str) -> str:
    response = httpx.post(
        f"{str(settings.ollama_url).rstrip('/')}/api/generate",
        json={
            "model": settings.ollama_model,
            "stream": False,
            "prompt": f"{SYSTEM_PROMPT}\n\nФрагменты:\n{context}\n\nВопрос: {question}",
        },
        timeout=settings.request_timeout,
    )
    response.raise_for_status()
    return response.json().get("response", "").strip()


def answer(question: str, hits: list[SearchHit]) -> tuple[str, str]:
    """Возвращает (ответ, использованный бэкенд)."""

    backend = settings.generation_backend
    if backend == "extractive" or not hits:
        return _extractive(question, hits), "extractive"

    context = build_context(hits, settings.max_context_chars)
    try:
        if backend == "anthropic":
            return _anthropic(question, context), backend
        if backend == "openai":
            return _openai(question, context), backend
        return _ollama(question, context), backend
    except Exception:
        # Провайдер недоступен — отдаём найденное как есть, а не 500:
        # поиск отработал, и его результат сам по себе является ответом.
        return _extractive(question, hits), "extractive-fallback"
