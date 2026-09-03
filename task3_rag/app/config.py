"""Настройки сервиса.

Ключей провайдеров может не быть — сервис обязан подниматься и отвечать всё
равно, иначе проверяющий не запустит его у себя. Поэтому провайдер выбирается
по наличию ключа, а не по флагу в конфиге.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    chunk_size: int = int(os.getenv("RAG_CHUNK_SIZE", "700"))
    chunk_overlap: int = int(os.getenv("RAG_CHUNK_OVERLAP", "150"))
    top_k: int = int(os.getenv("RAG_TOP_K", "4"))

    embed_model: str = os.getenv("RAG_EMBED_MODEL", "text-embedding-3-small")
    openai_key: str | None = os.getenv("OPENAI_API_KEY")
    anthropic_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    ollama_url: str | None = os.getenv("OLLAMA_URL")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1")

    request_timeout: float = float(os.getenv("RAG_TIMEOUT", "30"))
    max_context_chars: int = int(os.getenv("RAG_MAX_CONTEXT", "6000"))

    @property
    def embedding_backend(self) -> str:
        return "openai" if self.openai_key else "local"

    @property
    def generation_backend(self) -> str:
        if self.anthropic_key:
            return "anthropic"
        if self.openai_key:
            return "openai"
        if self.ollama_url:
            return "ollama"
        return "extractive"


settings = Settings()
