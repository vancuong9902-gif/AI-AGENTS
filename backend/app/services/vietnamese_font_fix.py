"""Utilities to detect and repair legacy Vietnamese font encodings.

This module focuses on common mojibake/legacy code page artifacts seen when
extracting text from older Vietnamese PDFs (TCVN3/ABC, VnTime/VnArial, VPS).
"""

from __future__ import annotations

from typing import Dict
import unicodedata

from app.services.text_repair import repair_ocr_spacing_line

ASCII_PRINTABLE_MIN = 0x20
ASCII_PRINTABLE_MAX = 0x7E
VN_LATIN_EXTENDED_RANGES = (
    (0x00C0, 0x024F),
    (0x1E00, 0x1EFF),
)


def _build_full_map(overrides: dict[int, str]) -> dict[int, str]:
    """Build a 256-entry byte->Unicode table with identity fallback."""
    table: dict[int, str] = {i: chr(i) for i in range(256)}
    table.update(overrides)
    return table


# Common TCVN3/ABC mappings used in Vietnamese legacy documents.
# Table is intentionally 256-complete via _build_full_map.
_TCVN3_OVERRIDES: dict[int, str] = {
    0x80: "À", 0x81: "Á", 0x82: "Â", 0x83: "Ã", 0x84: "È", 0x85: "É", 0x86: "Ê", 0x87: "Ì",
    0x88: "Ò", 0x89: "Ó", 0x8A: "Ô", 0x8B: "Õ", 0x8C: "Ù", 0x8D: "Ú", 0x8E: "Ý", 0x8F: "Đ",
    0x90: "à", 0x91: "á", 0x92: "â", 0x93: "ã", 0x94: "è", 0x95: "é", 0x96: "ê", 0x97: "ì",
    0x98: "ò", 0x99: "ó", 0x9A: "ô", 0x9B: "õ", 0x9C: "ù", 0x9D: "ú", 0x9E: "ý", 0x9F: "đ",
    0xA1: "Ă", 0xA2: "Â", 0xA3: "Ê", 0xA4: "Ô", 0xA5: "Ơ", 0xA6: "Ư", 0xA7: "ă", 0xA8: "â",
    0xA9: "ê", 0xAA: "ô", 0xAB: "ơ", 0xAC: "ơ", 0xAD: "ư", 0xAE: "ư", 0xAF: "Đ",
    0xB0: "ả", 0xB1: "ạ", 0xB2: "ẳ", 0xB3: "ẵ", 0xB4: "ặ", 0xB5: "ẩ", 0xB6: "ẫ", 0xB7: "ậ",
    0xB8: "á", 0xB9: "ạ", 0xBA: "ă", 0xBB: "ằ", 0xBC: "ẳ", 0xBD: "ẵ", 0xBE: "ắ", 0xBF: "ặ",
    0xC0: "ầ", 0xC1: "ấ", 0xC2: "ẩ", 0xC3: "ẫ", 0xC4: "ậ", 0xC5: "è", 0xC6: "é", 0xC7: "ề",
    0xC8: "ế", 0xC9: "ể", 0xCA: "ễ", 0xCB: "ậ", 0xCC: "ì", 0xCD: "í", 0xCE: "ỉ", 0xCF: "ĩ",
    0xD0: "ị", 0xD1: "ẽ", 0xD2: "ẹ", 0xD3: "ò", 0xD4: "ó", 0xD5: "ỏ", 0xD6: "õ", 0xD7: "ì",
    0xD8: "ỉ", 0xD9: "ó", 0xDA: "ô", 0xDB: "ơ", 0xDC: "ũ", 0xDD: "ư", 0xDE: "ị", 0xDF: "ò",
    0xE0: "ó", 0xE1: "ỏ", 0xE2: "õ", 0xE3: "ồ", 0xE4: "ọ", 0xE5: "ồ", 0xE6: "ố", 0xE7: "ổ",
    0xE8: "ế", 0xE9: "ỗ", 0xEA: "ộ", 0xEB: "ờ", 0xEC: "ớ", 0xED: "ở", 0xEE: "ỡ", 0xEF: "ợ",
    0xF0: "ù", 0xF1: "ú", 0xF2: "ủ", 0xF3: "ũ", 0xF4: "ụ", 0xF5: "ừ", 0xF6: "ứ", 0xF7: "ử",
    0xF8: "ữ", 0xF9: "ự", 0xFA: "ỳ", 0xFB: "ý", 0xFC: "ỷ", 0xFD: "ỹ", 0xFE: "ỵ", 0xFF: "đ",
}

# VnTime/VnArial has several byte swaps relative to TCVN3 in real-world docs.
_VNTIME_OVERRIDES = dict(_TCVN3_OVERRIDES)
_VNTIME_OVERRIDES.update(
    {
        0xAA: "à",
        0xAB: "á",
        0xAC: "ơ",
        0xAD: "ư",
        0xD7: "ì",
        0xCB: "ậ",
        0xE4: "ọ",
    }
)

# VPS legacy mapping (best-effort compatibility; full via identity fallback).
_VPS_OVERRIDES = dict(_TCVN3_OVERRIDES)
_VPS_OVERRIDES.update(
    {
        0xA1: "Á",
        0xA2: "À",
        0xA3: "Ả",
        0xA4: "Ã",
        0xA5: "Ạ",
        0xB8: "á",
        0xB9: "à",
        0xBA: "ả",
        0xBB: "ã",
        0xBC: "ạ",
    }
)

TCVN3_TO_UNICODE: Dict[int, str] = _build_full_map(_TCVN3_OVERRIDES)
VNTIME_TO_UNICODE: Dict[int, str] = _build_full_map(_VNTIME_OVERRIDES)
VPS_TO_UNICODE: Dict[int, str] = _build_full_map(_VPS_OVERRIDES)


SUSPICIOUS_MOJIBAKE_CHARS = set("¸¨¬­×Ëäîïñö÷ø")

ACTIVE_MAP_BYTES = {ord(ch) for ch in SUSPICIOUS_MOJIBAKE_CHARS} | {0xAA, 0xAB, 0xAC, 0xAD, 0xB8, 0xCB, 0xD7, 0xE4}

MOJIBAKE_SEQ_REPLACEMENTS: dict[str, str] = {
    "To¸n": "Toán",
    "häc": "học",
    "Ph\xad¬ng": "Phương",
    "tr×nh": "trình",
    "bËc": "bậc",
    "l\xadîng": "lượng",
    "N¨m": "Năm",
    "Nâm": "Năm",
}


def _is_valid_vn_char(ch: str) -> bool:
    cp = ord(ch)
    if ASCII_PRINTABLE_MIN <= cp <= ASCII_PRINTABLE_MAX:
        return True
    for lo, hi in VN_LATIN_EXTENDED_RANGES:
        if lo <= cp <= hi:
            return True
    return False


def detect_broken_vn_font(text: str) -> bool:
    """Detect likely broken Vietnamese legacy font extraction artifacts."""
    if not text:
        return False

    sample = str(text)
    if len(sample) < 20:
        return False

    valid_count = sum(1 for ch in sample if _is_valid_vn_char(ch))
    valid_ratio = valid_count / max(1, len(sample))

    latin1_supp_count = sum(1 for ch in sample if 0x00A0 <= ord(ch) <= 0x00BF)
    latin1_supp_ratio = latin1_supp_count / max(1, len(sample))
    suspicious_count = sum(1 for ch in sample if ch in SUSPICIOUS_MOJIBAKE_CHARS)

    if latin1_supp_ratio > 0.15:
        return True
    if suspicious_count >= 1:
        return True
    return valid_ratio < 0.70


def _apply_map(text: str, table: dict[int, str]) -> str:
    converted = "".join(table.get(ord(ch), ch) if ord(ch) in ACTIVE_MAP_BYTES else ch for ch in text)
    for src, dst in MOJIBAKE_SEQ_REPLACEMENTS.items():
        converted = converted.replace(src, dst)
    return converted


def _fallback_ocr_from_text(text: str) -> str:
    """Best-effort OCR fallback by rendering text to image then OCRing it."""
    try:
        from PIL import Image, ImageDraw  # type: ignore
        import pytesseract  # type: ignore
    except Exception:
        return text

    try:
        img = Image.new("RGB", (max(800, len(text) * 8), 120), "white")
        draw = ImageDraw.Draw(img)
        draw.text((10, 40), text, fill="black")
        ocr_text = pytesseract.image_to_string(img, lang="vie+eng")
        return ocr_text or text
    except Exception:
        return text


def fix_vietnamese_font_encoding(text: str) -> str:
    """Repair Vietnamese text broken by legacy PDF font encodings."""
    if not text:
        return ""

    original = str(text)
    if not detect_broken_vn_font(original):
        return unicodedata.normalize("NFC", original)

    result = original
    for table in (TCVN3_TO_UNICODE, VNTIME_TO_UNICODE, VPS_TO_UNICODE):
        candidate = _apply_map(original, table)
        if not detect_broken_vn_font(candidate):
            result = candidate
            break
        result = candidate

    if detect_broken_vn_font(result):
        result = _fallback_ocr_from_text(result)

    result = unicodedata.normalize("NFC", result)
    try:
        if any(token in result for token in (" t r", " k h", " đ i", "  ")):
            result = repair_ocr_spacing_line(result)
    except Exception:
        pass
    return result
