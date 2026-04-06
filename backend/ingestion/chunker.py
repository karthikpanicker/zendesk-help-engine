"""
Simple recursive character splitter. No external dependencies.
Splits on paragraphs → sentences → characters, with overlap between chunks.
"""

from __future__ import annotations

import re


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
    """
    Split *text* into chunks of at most *chunk_size* characters,
    with *overlap* characters of context carried into the next chunk.
    """
    text = text.strip()
    if not text:
        return []

    # Try to split on natural boundaries in order of preference
    separators = ["\n\n", "\n", ". ", " ", ""]
    chunks: list[str] = []
    _split(text, separators, chunk_size, overlap, chunks)
    return [c.strip() for c in chunks if c.strip()]


def _split(
    text: str,
    separators: list[str],
    chunk_size: int,
    overlap: int,
    result: list[str],
) -> None:
    if len(text) <= chunk_size:
        result.append(text)
        return

    sep = separators[0] if separators else ""
    remaining_seps = separators[1:]

    if sep:
        parts = re.split(re.escape(sep), text)
    else:
        parts = list(text)

    current: list[str] = []
    current_len = 0

    for part in parts:
        part_len = len(part) + len(sep)
        if current_len + part_len > chunk_size and current:
            chunk = sep.join(current)
            if len(chunk) > chunk_size and remaining_seps:
                # Chunk is still too big — recurse with finer separator
                _split(chunk, remaining_seps, chunk_size, overlap, result)
            else:
                result.append(chunk)
            # Carry overlap into next chunk
            overlap_text = sep.join(current)[-overlap:] if overlap else ""
            current = [overlap_text] if overlap_text else []
            current_len = len(overlap_text)

        current.append(part)
        current_len += part_len

    if current:
        leftover = sep.join(current)
        if len(leftover) > chunk_size and remaining_seps:
            _split(leftover, remaining_seps, chunk_size, overlap, result)
        else:
            result.append(leftover)
