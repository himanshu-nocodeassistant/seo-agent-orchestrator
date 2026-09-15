"""Pure helpers for placing untrusted Webflow text in model prompts."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


# Role claims are treated as control syntax only at the start of a line. A
# normal sentence such as "Contact user: support" is therefore left alone.
_ROLE_MARKER = re.compile(
    r"^(?P<indent>[ \t]*)(?:system|developer|assistant|user)\s*:\s*",
    re.IGNORECASE | re.MULTILINE,
)


def sanitize_untrusted_text(text: str) -> str:
    """Remove invisible controls and line-start role claims from *text*.

    Ordinary visible characters and whitespace are not normalised. The text
    after a removed role marker remains in place, so this is not truncation.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    without_controls = "".join(
        character
        for character in text
        if character in "\t\n\r" or unicodedata.category(character) not in {"Cc", "Cf"}
    )
    return _ROLE_MARKER.sub(lambda match: match.group("indent"), without_controls)


def fence_prompt_text(text: str, label: str = "untrusted-content") -> str:
    """Return sanitized text inside a simple, model-readable XML fence."""
    if not isinstance(label, str) or not label.strip():
        raise ValueError("label must be a non-empty string")
    tag = re.sub(r"[^a-zA-Z0-9_-]+", "-", label.strip()).strip("-").lower()
    if not tag:
        raise ValueError("label must contain a tag character")
    safe_text = sanitize_untrusted_text(text)
    return f"<{tag}>\n{safe_text}\n</{tag}>"


@dataclass(frozen=True)
class ContextChunk:
    """One complete, ordered slice of the original source text."""

    text: str
    metadata: dict[str, int]


@dataclass(frozen=True)
class ChunkedContext:
    """All context chunks and metadata needed to reason about coverage."""

    text: str
    chunks: tuple[ContextChunk, ...]
    metadata: dict[str, Any]


def chunk_for_model_context(text: str, max_chars: int) -> ChunkedContext:
    """Split source text into bounded chunks without silently dropping text."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not isinstance(max_chars, int) or isinstance(max_chars, bool) or max_chars <= 0:
        raise ValueError("max_chars must be a positive integer")

    pieces = tuple(text[index : index + max_chars] for index in range(0, len(text), max_chars))
    chunks = tuple(
        ContextChunk(
            piece,
            {
                "index": index,
                "start": index * max_chars,
                "end": index * max_chars + len(piece),
                "length": len(piece),
                "total_chunks": len(pieces),
            },
        )
        for index, piece in enumerate(pieces)
    )
    return ChunkedContext(
        text=text,
        chunks=chunks,
        metadata={
            "source_length": len(text),
            "max_chars": max_chars,
            "chunk_count": len(chunks),
            "truncated": False,
        },
    )
