"""
Vietnamese font fix utilities for PDF/Word export.
Ensures proper rendering of Vietnamese diacritics (ắ, ặ, ổ, ồ, etc.)
"""
from __future__ import annotations
import unicodedata
import re


def normalize_vietnamese(text: str) -> str:
    """Normalize Vietnamese text to ensure consistent encoding."""
    if not text:
        return text
    return unicodedata.normalize("NFC", text)


def strip_control_characters(text: str) -> str:
    """Remove BOM and control characters that break font rendering."""
    text = text.lstrip("\ufeff\ufffe")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text


def fix_vietnamese_text(text: str) -> str:
    """Full pipeline: strip BOM + control chars + normalize."""
    if not text:
        return text
    text = strip_control_characters(text)
    text = normalize_vietnamese(text)
    return text


def get_safe_font_name() -> str:
    """Return the recommended font name for Vietnamese in docx/pdf."""
    return "Times New Roman"


VIETNAMESE_DOCX_FONT = "Times New Roman"
VIETNAMESE_PDF_FONT = "Helvetica"
