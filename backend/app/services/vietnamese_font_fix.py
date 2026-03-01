"""Utilities for detecting and fixing legacy Vietnamese font encodings.

This module targets common mojibake patterns produced by old Vietnamese fonts
(TCVN3/ABC, VnTime/VnArial, VPS) when PDF text extraction loses CMap data.
"""

from __future__ import annotations

import tempfile
import unicodedata
import re
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

_VNI_TYPING_RX = re.compile(r"(?i)(?:a|e|i|o|u|y|d)[0-9]")


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
_VNI_TYPING_PATTERN = re.compile(r"(?i)(?:[aeiouyăâêôơư][1-5]|[aeou][678]|d9)")
_VNI_BASE_MAP: dict[str, dict[str, str]] = {
    "a": {"6": "â", "8": "ă"},
    "A": {"6": "Â", "8": "Ă"},
    "e": {"6": "ê"},
    "E": {"6": "Ê"},
    "o": {"6": "ô", "7": "ơ"},
    "O": {"6": "Ô", "7": "Ơ"},
    "u": {"7": "ư"},
    "U": {"7": "Ư"},
}
_VNI_TONE_MAP = {"1": "\u0301", "2": "\u0300", "3": "\u0309", "4": "\u0303", "5": "\u0323"}


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


def detect_vni_typing(text: str) -> bool:
    """Detect VNI typing-number patterns such as 'Toa1n ho5c'."""
    if not text:
        return False
    sample = text[:80]
    return len(_VNI_TYPING_RX.findall(sample)) >= 3


_VNI_BASE_MAP: dict[str, str] = {
    "a": "a", "e": "e", "i": "i", "o": "o", "u": "u", "y": "y",
    "A": "A", "E": "E", "I": "I", "O": "O", "U": "U", "Y": "Y",
}
_VNI_MODIFIER_MAP: dict[str, dict[str, str]] = {
    "a": {"6": "â", "7": "ă"},
    "A": {"6": "Â", "7": "Ă"},
    "e": {"6": "ê"},
    "E": {"6": "Ê"},
    "o": {"6": "ô", "7": "ơ"},
    "O": {"6": "Ô", "7": "Ơ"},
    "u": {"7": "ư"},
    "U": {"7": "Ư"},
}
_VNI_TONE_MAP: dict[str, int] = {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5}
_VNI_TONE_COMBINING: dict[str, str] = {
    "1": "\u0301",  # sắc
    "2": "\u0300",  # huyền
    "3": "\u0309",  # hỏi
    "4": "\u0303",  # ngã
    "5": "\u0323",  # nặng
}


def _apply_tone(base_char: str, tone_digit: str) -> str:
    mark = _VNI_TONE_COMBINING.get(tone_digit)
    if not mark:
        return base_char
    return unicodedata.normalize("NFC", f"{base_char}{mark}")


def _build_vni_replacement_map() -> dict[str, str]:
    replacements: dict[str, str] = {"d9": "đ", "D9": "Đ"}

    for base, plain in _VNI_BASE_MAP.items():
        for tone in _VNI_TONE_MAP:
            replacements[f"{base}{tone}"] = _apply_tone(plain, tone)

    for base, mod_map in _VNI_MODIFIER_MAP.items():
        for mod, modded in mod_map.items():
            replacements[f"{base}{mod}"] = modded
            for tone in _VNI_TONE_MAP:
                replacements[f"{base}{mod}{tone}"] = _apply_tone(modded, tone)

    return replacements


_VNI_REPLACEMENTS = _build_vni_replacement_map()
_VNI_KEYS_SORTED = sorted(_VNI_REPLACEMENTS.keys(), key=len, reverse=True)
_VNI_CONVERT_RX = re.compile("|".join(re.escape(k) for k in _VNI_KEYS_SORTED))


def convert_vni_typing_to_unicode(text: str) -> str:
    """Convert common VNI numeric typing to Unicode Vietnamese (longest-first)."""
    if not text:
        return ""
    converted = _VNI_CONVERT_RX.sub(lambda m: _VNI_REPLACEMENTS.get(m.group(0), m.group(0)), text)
    return unicodedata.normalize("NFC", converted)


def looks_garbled_short_title(text: str) -> bool:
    """Heuristic for short garbled titles containing tofu/unknown/suspicious chars."""
    if not text:
        return False
    s = str(text).strip()
    if not s or len(s) >= 150:
        return False

    total = len(s)
    hard_suspects = sum(1 for ch in s if ch in {"?", "□", "�"})
    odd_chars = 0
    for ch in s:
        if ch.isspace() or ch.isalnum() or ch in "-–—:;,.()/%&+[]'\"_":
            continue
        if unicodedata.category(ch).startswith("P"):
            continue
        if any(lo <= ord(ch) <= hi for lo, hi in VALID_RANGES):
            continue
        odd_chars += 1

    suspicious = hard_suspects + odd_chars
    ratio = suspicious / max(1, total)
    return suspicious >= 2 and ratio >= 0.08


def llm_repair_title_if_needed(title: str) -> str:
    """Attempt LLM-only repair for short garbled titles; fallback to original text."""
    source = str(title or "")
    if not source or not looks_garbled_short_title(source):
        return source

    try:
        from app.services.llm_service import chat_text, llm_available

        if not llm_available():
            return source
        repaired = chat_text(
            (
                "Sửa tiêu đề tiếng Việt bị lỗi encoding/mất dấu bên dưới. "
                "Chỉ trả về đúng một tiêu đề đã sửa, không giải thích, không thêm tiền tố.\n\n"
                f"Tiêu đề lỗi: {source}"
            ),
            temperature=0.0,
            max_tokens=60,
        )
        repaired_text = str(repaired or "").strip()
        return unicodedata.normalize("NFC", repaired_text) if repaired_text else source
    except Exception:
        return source


def _map_with_table(text: str, table: dict[int, str]) -> str:
    mapped_chars: list[str] = []
    for ch in text:
        cp = ord(ch)
        if cp <= 0xFF and cp in ACTIVE_MAP_BYTES:
            mapped_chars.append(table.get(cp, ch))
        else:
            mapped_chars.append(ch)
    return unicodedata.normalize("NFC", "".join(mapped_chars))


def detect_vni_typing(text: str, *, min_matches: int = 3, window_size: int = 60) -> bool:
    """Detect VNI numeric-typing artifacts (e.g., Toa1n, ho5c, d9)."""
    source = str(text or "")
    if not source:
        return False

    for start in range(0, len(source), max(1, window_size // 2)):
        window = source[start: start + window_size]
        if not window:
            continue
        if len(_VNI_TYPING_PATTERN.findall(window)) >= int(min_matches):
            return True
    return False


def _convert_vni_token(token: str) -> str:
    chars = list(token)
    original_len = len(chars)
    i = 0
    while i < len(chars):
        ch = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if ch in ("d", "D") and nxt == "9":
            chars[i] = "đ" if ch == "d" else "Đ"
            del chars[i + 1]
            continue
        if nxt in _VNI_BASE_MAP.get(ch, {}):
            chars[i] = _VNI_BASE_MAP[ch][nxt]
            del chars[i + 1]
            continue
        if nxt in _VNI_TONE_MAP and ch.lower() in "aeiouyăâêôơư" and original_len > 2:
            chars[i] = unicodedata.normalize("NFC", f"{ch}{_VNI_TONE_MAP[nxt]}")
            del chars[i + 1]
            continue
        i += 1

    converted = "".join(chars)
    # Common heading typo after OCR/VNI mix: "lơp" -> "lớp".
    converted = re.sub(r"\blơp\b", "lớp", converted)
    converted = re.sub(r"\bLơp\b", "Lớp", converted)
    return converted


def convert_vni_typing_to_unicode(text: str) -> str:
    """Convert common VNI number-typing Vietnamese sequences to Unicode NFC."""
    source = str(text or "")
    if not source:
        return ""

    converted = re.sub(r"[A-Za-zÀ-ỹà-ỹ0-9]+", lambda m: _convert_vni_token(m.group(0)), source)
    return unicodedata.normalize("NFC", converted)


def _llm_repair_short_vietnamese_title(text: str) -> str:
    source = str(text or "").strip()
    if not source or len(source) > 120:
        return source
    try:
        from app.services.llm_service import chat_text, llm_available

        if not llm_available():
            return source
        repaired = chat_text(
            messages=[
                {"role": "system", "content": "Bạn sửa lỗi encoding tiếng Việt chính xác, giữ nguyên ý nghĩa."},
                {
                    "role": "user",
                    "content": "Sửa tiêu đề tiếng Việt bị lỗi encoding thành đúng, chỉ trả về title đã sửa.\n"
                    f"Title: {source}",
                },
            ],
            temperature=0.0,
            max_tokens=120,
        ).strip()
    except Exception:
        return source

    if not repaired:
        return source
    return unicodedata.normalize("NFC", repaired.splitlines()[0].strip() or source)


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
        result = text
        if detect_vni_typing(result):
            result = convert_vni_typing_to_unicode(result)
        if len(result) < 150 and looks_garbled_short_title(result):
            result = llm_repair_title_if_needed(result)
        return unicodedata.normalize("NFC", result)

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

    if detect_vni_typing(result):
        result = convert_vni_typing_to_unicode(result)
        if not detect_broken_vn_font(result):
            return unicodedata.normalize("NFC", result)

    llm_repaired = _llm_repair_short_vietnamese_title(result)
    if llm_repaired and llm_repaired != result:
        return unicodedata.normalize("NFC", llm_repaired)

    result = _fallback_tesseract(result)
    if detect_vni_typing(result):
        result = convert_vni_typing_to_unicode(result)
    if len(result) < 150 and looks_garbled_short_title(result):
        result = llm_repair_title_if_needed(result)
    return unicodedata.normalize("NFC", result)


def fix_vietnamese_encoding(text: str) -> str:
    """Backward-compatible alias used by pipeline/services."""
    return fix_vietnamese_font_encoding(text)


_MOJIBAKE_PATTERNS = ("áº", "â€", "Ä", "Ã", "Â")


def _looks_like_vietnamese(text: str) -> bool:
    vn_chars = re.findall(r"[àáảãạăắằẳẵặâấầẩẫậđèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ]", text.lower())
    vn_words = re.findall(r"\b(?:và|của|những|trong|không|được|học|bài|chương|phương|trình)\b", text.lower())
    return len(vn_chars) >= 2 or len(vn_words) >= 2


def fix_mojibake_topic(text: str) -> str:
    """Fix common mojibake topic titles without worsening clean text."""
    source = str(text or "")
    if not source:
        return ""

    if not any(marker in source for marker in _MOJIBAKE_PATTERNS):
        return source

    for enc in ("cp1252", "latin-1", "windows-1252"):
        try:
            repaired = source.encode(enc).decode("utf-8").strip()
        except Exception:
            continue
        if repaired and _looks_like_vietnamese(repaired):
            return unicodedata.normalize("NFC", repaired)

    return source


def get_noto_sans_font_path() -> str | None:
    for path in NOTO_SANS_CANDIDATES:
        if Path(path).exists():
            return path
    return None
