"""Utilities for detecting and fixing legacy Vietnamese font encodings.

This module targets common mojibake patterns produced by old Vietnamese fonts
(TCVN3/ABC, VnTime/VnArial, VPS) when PDF text extraction loses CMap data.
"""

from __future__ import annotations

import tempfile
import unicodedata
from pathlib import Path
from typing import Dict

ASCII_PRINTABLE_MIN = 0x20
ASCII_PRINTABLE_MAX = 0x7E
VALID_RANGES = ((0x00C0, 0x024F), (0x1E00, 0x1EFF))
FAST_PATH_CHARS = {"¸", "\u00ad", "¬", "×", "®", "¦", "§", "©", "¹", "µ", "°", "±"}
EXTRA_SUSPECT_CHARS = {"¨", "ä", "Ë", "Ö", "î"}
ACTIVE_MAP_BYTES = {0xA8, 0xAC, 0xAD, 0xAE, 0xB5, 0xB8, 0xB9, 0xCB, 0xD6, 0xD7, 0xE4, 0xEE}
NOTO_SANS_CANDIDATES = (
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDisplay-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSans-Regular.ttf",
)


def _build_256_map(overrides: dict[int, str]) -> dict[int, str]:
    """Build a complete 256-entry byte mapping table."""
    table = {i: chr(i) for i in range(256)}
    table.update(overrides)
    return table


# TCVN3 (ABC) complete 256 entries through identity + explicit overrides.
_TCVN3_OVERRIDES: dict[int, str] = {
    0x80: "À", 0x81: "Á", 0x82: "Â", 0x83: "Ã", 0x84: "È", 0x85: "É", 0x86: "Ê", 0x87: "Ì",
    0x88: "Ò", 0x89: "Ó", 0x8A: "Ô", 0x8B: "Õ", 0x8C: "Ù", 0x8D: "Ú", 0x8E: "Ý", 0x8F: "Đ",
    0x90: "à", 0x91: "á", 0x92: "â", 0x93: "ã", 0x94: "è", 0x95: "é", 0x96: "ê", 0x97: "ì",
    0x98: "ò", 0x99: "ó", 0x9A: "ô", 0x9B: "õ", 0x9C: "ù", 0x9D: "ú", 0x9E: "ý", 0x9F: "đ",
    0xA1: "Ă", 0xA2: "Â", 0xA3: "Ê", 0xA4: "Ô", 0xA5: "Ơ", 0xA6: "Ư", 0xA7: "ă", 0xA8: "ă",
    0xA9: "ê", 0xAA: "ô", 0xAB: "ơ", 0xAC: "ơ", 0xAD: "ư", 0xAE: "đ", 0xAF: "ư",
    0xB0: "à", 0xB1: "ả", 0xB2: "ã", 0xB3: "á", 0xB4: "ạ", 0xB5: "à", 0xB6: "ả", 0xB7: "ã",
    0xB8: "á", 0xB9: "ạ", 0xBA: "ằ", 0xBB: "ẳ", 0xBC: "ẵ", 0xBD: "ắ", 0xBE: "ặ", 0xBF: "ầ",
    0xC0: "ẩ", 0xC1: "ẫ", 0xC2: "ấ", 0xC3: "ậ", 0xC4: "è", 0xC5: "ẻ", 0xC6: "ẽ", 0xC7: "é",
    0xC8: "ẹ", 0xC9: "ề", 0xCA: "ể", 0xCB: "ậ", 0xCC: "ế", 0xCD: "ệ", 0xCE: "ì", 0xCF: "ỉ",
    0xD0: "ĩ", 0xD1: "í", 0xD2: "ị", 0xD3: "ò", 0xD4: "ỏ", 0xD5: "õ", 0xD6: "ệ", 0xD7: "ì",
    0xD8: "ọ", 0xD9: "ồ", 0xDA: "ổ", 0xDB: "ỗ", 0xDC: "ố", 0xDD: "ộ", 0xDE: "ờ", 0xDF: "ở",
    0xE0: "ỡ", 0xE1: "ớ", 0xE2: "ợ", 0xE3: "ù", 0xE4: "ọ", 0xE5: "ũ", 0xE6: "ú", 0xE7: "ụ",
    0xE8: "ừ", 0xE9: "ử", 0xEA: "ữ", 0xEB: "ứ", 0xEC: "ự", 0xED: "ỳ", 0xEE: "ợ", 0xEF: "ý",
    0xF0: "ỷ", 0xF1: "ỹ", 0xF2: "ỵ", 0xF3: "Ă", 0xF4: "ắ", 0xF5: "ằ", 0xF6: "ẳ", 0xF7: "ẵ",
    0xF8: "ặ", 0xF9: "Â", 0xFA: "ấ", 0xFB: "ầ", 0xFC: "ẩ", 0xFD: "ẫ", 0xFE: "ậ", 0xFF: "đ",
}

# VnTime/VnArial: differs mainly in 0x80-0x9F handling in old Word-era documents.
_VNTIME_OVERRIDES = dict(_TCVN3_OVERRIDES)
_VNTIME_OVERRIDES.update(
    {
        0x80: "€", 0x81: "", 0x82: "‚", 0x83: "ƒ", 0x84: "„", 0x85: "…", 0x86: "†", 0x87: "‡",
        0x88: "ˆ", 0x89: "‰", 0x8A: "Š", 0x8B: "‹", 0x8C: "Œ", 0x8D: "", 0x8E: "Ž", 0x8F: "",
        0x90: "", 0x91: "‘", 0x92: "’", 0x93: "“", 0x94: "”", 0x95: "•", 0x96: "–", 0x97: "—",
        0x98: "˜", 0x99: "™", 0x9A: "š", 0x9B: "›", 0x9C: "œ", 0x9D: "", 0x9E: "ž", 0x9F: "Ÿ",
    }
)

# VPS map: keep complete 256 entries, with VPS-specific high-byte adjustments.
_VPS_OVERRIDES = dict(_TCVN3_OVERRIDES)
_VPS_OVERRIDES.update(
    {
        0x80: "Ạ", 0x81: "Ả", 0x82: "Ấ", 0x83: "Ầ", 0x84: "Ẩ", 0x85: "Ẫ", 0x86: "Ậ", 0x87: "Ắ",
        0x88: "Ằ", 0x89: "Ẳ", 0x8A: "Ẵ", 0x8B: "Ặ", 0x8C: "Ẹ", 0x8D: "Ẻ", 0x8E: "Ẽ", 0x8F: "Ế",
        0x90: "Ề", 0x91: "Ể", 0x92: "Ễ", 0x93: "Ệ", 0x94: "Ỉ", 0x95: "Ị", 0x96: "Ọ", 0x97: "Ỏ",
        0x98: "Ỗ", 0x99: "Ộ", 0x9A: "Ớ", 0x9B: "Ờ", 0x9C: "Ở", 0x9D: "Ỡ", 0x9E: "Ợ", 0x9F: "Ụ",
    }
)

TCVN3_TO_UNICODE: Dict[int, str] = _build_256_map(_TCVN3_OVERRIDES)
VNTIME_TO_UNICODE: Dict[int, str] = _build_256_map(_VNTIME_OVERRIDES)
VPS_TO_UNICODE: Dict[int, str] = _build_256_map(_VPS_OVERRIDES)


def _is_valid_char(ch: str) -> bool:
    cp = ord(ch)
    if ASCII_PRINTABLE_MIN <= cp <= ASCII_PRINTABLE_MAX:
        return True
    return any(lo <= cp <= hi for lo, hi in VALID_RANGES)


def detect_broken_vn_font(text: str) -> bool:
    """Detect likely legacy Vietnamese font corruption."""
    if not text:
        return False

    suspicious_count = sum(1 for ch in text if ch in FAST_PATH_CHARS)
    if suspicious_count >= 3:
        return True

    if any(ch in FAST_PATH_CHARS or ch in EXTRA_SUSPECT_CHARS for ch in text):
        return True

    if len(text) < 15:
        return False

    valid_count = sum(1 for ch in text if _is_valid_char(ch))
    ratio = valid_count / max(1, len(text))
    return ratio < 0.70


def _map_with_table(text: str, table: dict[int, str]) -> str:
    mapped_chars: list[str] = []
    for ch in text:
        cp = ord(ch)
        if cp <= 0xFF and cp in ACTIVE_MAP_BYTES:
            mapped_chars.append(table.get(cp, ch))
        else:
            mapped_chars.append(ch)
    return unicodedata.normalize("NFC", "".join(mapped_chars))


def _fallback_tesseract(text: str) -> str:
    """Fallback OCR attempt by rendering text to temporary PNG."""
    try:
        import pytesseract  # type: ignore
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except Exception:
        return text

    try:
        width = max(1000, len(text) * 18)
        height = 140
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        draw.text((20, 45), text, fill="black", font=font)

        with tempfile.TemporaryDirectory(prefix="vn-font-fix-") as tmp_dir:
            png_path = Path(tmp_dir) / "input.png"
            image.save(png_path)
            ocr_text = pytesseract.image_to_string(
                Image.open(png_path),
                lang="vie+eng",
                config="--psm 6",
            )
        return (ocr_text or text).strip() or text
    except Exception:
        return text


def fix_vietnamese_font_encoding(text: str) -> str:
    """Repair text broken by legacy Vietnamese font encodings."""
    if not text:
        return ""

    if not detect_broken_vn_font(text):
        return text

    result = text

    result = _map_with_table(text, TCVN3_TO_UNICODE)
    if not detect_broken_vn_font(result):
        return unicodedata.normalize("NFC", result)

    result = _map_with_table(text, VNTIME_TO_UNICODE)
    if not detect_broken_vn_font(result):
        return unicodedata.normalize("NFC", result)

    result = _map_with_table(text, VPS_TO_UNICODE)
    if not detect_broken_vn_font(result):
        return unicodedata.normalize("NFC", result)

    result = _fallback_tesseract(result)
    return unicodedata.normalize("NFC", result)


def fix_vietnamese_encoding(text: str) -> str:
    """Backward-compatible alias used by pipeline/services."""
    return fix_vietnamese_font_encoding(text)


def get_noto_sans_font_path() -> str | None:
    for path in NOTO_SANS_CANDIDATES:
        if Path(path).exists():
            return path
    return None
