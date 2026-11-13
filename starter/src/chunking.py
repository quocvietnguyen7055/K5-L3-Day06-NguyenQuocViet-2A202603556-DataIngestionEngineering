"""Deterministic page-local chunking strategies."""
import hashlib
import re

from .models import Chunk, DocumentPage


def _chunk(page: DocumentPage, text: str, ordinal: int) -> Chunk:
    key = f"{page.document_id}:{page.page}:{ordinal}:{text}"
    chunk_id = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return Chunk(chunk_id, page.document_id, page.source, page.page, text, dict(page.metadata))


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    if size < 1 or overlap < 0 or overlap >= size:
        raise ValueError("size must be positive and overlap must be in [0, size)")
    text = page.text.strip()
    if not text:
        return []
    stride = size - overlap
    return [_chunk(page, text[start:start + size], i)
            for i, start in enumerate(range(0, len(text), stride)) if text[start:start + size].strip()]


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    if max_size < 1:
        raise ValueError("max_size must be positive")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", page.text) if p.strip()]
    pieces: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) > max_size:
            # Split at sentence boundaries when possible, then hard-split any oversized sentence.
            sentences = re.split(r"(?<=[.!?。！？])\s+", paragraph)
            carry = ""
            for sentence in sentences:
                while len(sentence) > max_size:
                    if carry:
                        pieces.append(carry)
                        carry = ""
                    pieces.append(sentence[:max_size])
                    sentence = sentence[max_size:]
                candidate = f"{carry} {sentence}".strip()
                if carry and len(candidate) > max_size:
                    pieces.append(carry)
                    carry = sentence
                else:
                    carry = candidate
            if carry:
                pieces.append(carry)
        else:
            pieces.append(paragraph)
    result: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}\n\n{piece}".strip()
        if current and len(candidate) > max_size:
            result.append(current)
            current = piece
        else:
            current = candidate
    if current:
        result.append(current)
    return [_chunk(page, text, i) for i, text in enumerate(result)]
