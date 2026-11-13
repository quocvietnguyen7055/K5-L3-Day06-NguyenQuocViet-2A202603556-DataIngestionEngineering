"""Read PDF pages and normalize text while preserving paragraph boundaries."""
import unicodedata
from pathlib import Path

from pypdf import PdfReader

from .models import DocumentPage


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    reader = PdfReader(str(path))
    pages = []
    for number, pdf_page in enumerate(reader.pages, start=1):
        raw = pdf_page.extract_text() or ""
        text = normalize_text(raw)
        pages.append(DocumentPage(
            document_id=document_id, source=source, page=number, text=text,
            metadata={"extraction_status": "empty" if not text else "ok"},
        ))
    return pages


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    # Collapse horizontal whitespace but keep newlines, which are useful chunk boundaries.
    lines = [" ".join(line.split()) for line in text.split("\n")]
    paragraphs = "\n".join(line for line in lines if line)
    return paragraphs.strip()
