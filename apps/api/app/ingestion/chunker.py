from __future__ import annotations

import re
from dataclasses import dataclass

import tiktoken

_ENCODING = tiktoken.get_encoding("cl100k_base")

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.?!])\s+|(?<=\n\n)")


@dataclass(frozen=True)
class ChunkResult:
    text: str
    token_count: int
    index: int


def chunk_text(
    text: str,
    max_tokens: int = 700,
    overlap_tokens: int = 80,
) -> list[ChunkResult]:
    if not text.strip():
        return []

    tokens = _ENCODING.encode(text)

    if len(tokens) <= max_tokens:
        return [ChunkResult(text=text, token_count=len(tokens), index=0)]

    sentences = _split_sentences(text)
    chunks: list[ChunkResult] = []
    current_tokens: list[int] = []

    for sentence in sentences:
        sentence_tokens = _ENCODING.encode(sentence)

        if not sentence_tokens:
            continue

        if len(sentence_tokens) > max_tokens:
            if current_tokens:
                _emit(chunks, current_tokens)
                current_tokens = []
            step = max(1, max_tokens - overlap_tokens)
            for start in range(0, len(sentence_tokens), step):
                _emit(chunks, sentence_tokens[start : start + max_tokens])
            continue

        if len(current_tokens) + len(sentence_tokens) > max_tokens and current_tokens:
            _emit(chunks, current_tokens)
            current_tokens = current_tokens[-overlap_tokens:]

        current_tokens.extend(sentence_tokens)

    if current_tokens:
        _emit(chunks, current_tokens)

    return chunks


def _emit(chunks: list[ChunkResult], tokens: list[int]) -> None:
    chunks.append(
        ChunkResult(
            text=_ENCODING.decode(tokens),
            token_count=len(tokens),
            index=len(chunks),
        )
    )


def _split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_BOUNDARY.split(text)
    return [part.strip() + " " for part in parts if part.strip()]
