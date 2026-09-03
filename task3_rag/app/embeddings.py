"""Эмбеддинги: OpenAI, если есть ключ, иначе локальный детерминированный бэкенд.

Локальный бэкенд — хеширование словных и символьных 3-грамм в фиксированную
размерность с L2-нормировкой. Это не замена нормальной модели, но он не требует
сети и ключей, поэтому сервис поднимается и проходит тесты на чистой машине.
Для русского текста символьные n-граммы важнее словных: они переживают
словоизменение («штраф» / «штрафа» / «штрафы» дают общие n-граммы).
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

import httpx

from .config import settings

_WORD = re.compile(r"\w+", re.UNICODE)
_LOCAL_DIM = 512


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


class LocalEmbedder:
    """Хеширующий векторизатор без внешних зависимостей."""

    name = "local-hashing"

    def __init__(self, dim: int = _LOCAL_DIM) -> None:
        self.dim = dim

    def _features(self, text: str) -> list[str]:
        words = _WORD.findall(text.lower())
        feats = list(words)
        for word in words:
            padded = f"^{word}$"
            feats.extend(padded[i : i + 3] for i in range(max(len(padded) - 2, 1)))
        return feats

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for feat in self._features(text):
                digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
                idx = int.from_bytes(digest[:4], "big") % self.dim
                sign = 1.0 if digest[4] & 1 else -1.0
                vec[idx] += sign
            out.append(_normalize(vec))
        return out


class OpenAIEmbedder:
    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model
        self.dim = 1536

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": texts},
            timeout=settings.request_timeout,
        )
        response.raise_for_status()
        data = sorted(response.json()["data"], key=lambda item: item["index"])
        vectors = [_normalize(item["embedding"]) for item in data]
        self.dim = len(vectors[0]) if vectors else self.dim
        return vectors


def build_embedder() -> Embedder:
    if settings.openai_key:
        return OpenAIEmbedder(settings.openai_key, settings.embed_model)
    return LocalEmbedder()
