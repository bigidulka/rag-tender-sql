"""Разбиение документа на чанки.

Режем по границам абзацев и предложений, а не по символам вслепую: регламент
состоит из пунктов, и разрыв посреди пункта ломает и поиск, и цитирование.
Перекрытие оставляем, чтобы факт, лежащий на стыке, попал хотя бы в один чанк
целиком.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PARAGRAPH = re.compile(r"\n\s*\n")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    id: int
    text: str
    start: int
    end: int


def _split_long(block: str, limit: int) -> list[str]:
    if len(block) <= limit:
        return [block]
    out: list[str] = []
    buf = ""
    for sentence in _SENTENCE.split(block):
        if buf and len(buf) + len(sentence) + 1 > limit:
            out.append(buf.strip())
            buf = sentence
        else:
            buf = f"{buf} {sentence}".strip()
    if buf.strip():
        out.append(buf.strip())
    # Одно предложение длиннее лимита — режем жёстко, иначе чанк не влезет в окно.
    result: list[str] = []
    for piece in out:
        while len(piece) > limit:
            result.append(piece[:limit])
            piece = piece[limit:]
        if piece:
            result.append(piece)
    return result


def split_document(text: str, chunk_size: int, overlap: int) -> list[Chunk]:
    if overlap >= chunk_size:
        raise ValueError("overlap должен быть меньше chunk_size")

    blocks: list[str] = []
    for paragraph in _PARAGRAPH.split(text):
        paragraph = paragraph.strip()
        if paragraph:
            blocks.extend(_split_long(paragraph, chunk_size))

    bodies: list[str] = []
    buf = ""
    for block in blocks:
        if buf and len(buf) + len(block) + 2 > chunk_size:
            bodies.append(buf)
            tail = buf[-overlap:] if overlap else ""
            buf = f"{tail}\n\n{block}".strip() if tail else block
        else:
            buf = f"{buf}\n\n{block}".strip() if buf else block
    if buf.strip():
        bodies.append(buf)

    out: list[Chunk] = []
    cursor = 0
    for idx, body in enumerate(bodies):
        start = text.find(body[:40], cursor)
        if start < 0:
            start = cursor
        out.append(Chunk(id=idx, text=body, start=start, end=start + len(body)))
        cursor = max(cursor, start + 1)
    return out
