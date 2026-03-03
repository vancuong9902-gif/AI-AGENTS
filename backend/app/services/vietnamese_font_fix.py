"""
Vietnamese font fix utilities for PDF/Word export.
Ensures proper rendering of Vietnamese diacritics (ắ, ặ, ổ, ồ, etc.)
"""
from __future__ import annotations
import re
import unicodedata
from pathlib import Path


def normalize_vietnamese(text: str) -> str:
    """Normalize Vietnamese text to ensure consistent encoding."""
    if not text:
        return text
    return unicodedata.normalize("NFC", text)


def strip_control_characters(text: str) -> str:
    """Remove BOM and control characters that break font rendering."""
    text = text.lstrip("\ufeff\ufffe")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\xad]", "", text)
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


_VNI_TONE_MARKS = {
    "1": "\u0301",  # acute
    "2": "\u0300",  # grave
    "3": "\u0309",  # hook above
    "4": "\u0303",  # tilde
    "5": "\u0323",  # dot below
}

_VNI_BASE_MODIFIERS = {
    "a": {"6": "â", "8": "ă"},
    "A": {"6": "Â", "8": "Ă"},
    "e": {"6": "ê"},
    "E": {"6": "Ê"},
    "o": {"6": "ô", "7": "ơ"},
    "O": {"6": "Ô", "7": "Ơ"},
    "u": {"7": "ư"},
    "U": {"7": "Ư"},
    "d": {"9": "đ"},
    "D": {"9": "Đ"},
}


def detect_vni_typing(text: str, min_matches: int = 2, window_size: int = 24) -> bool:
    """Detect likely VNI typed Vietnamese (e.g. Toa1n, ho5c, lo7p)."""
    if not text:
        return False

    if re.search(r"[=+\-*/^]", text):
        # Formula-like text should not be treated as VNI typing.
        formula_hits = re.findall(r"\b[a-zA-Z]\d\b", text)
        if formula_hits and len(formula_hits) >= min_matches:
            return False

    pattern = re.compile(r"(?i)[a-zăâêôơưđ]{1,8}[1-9]{1,2}[a-zăâêôơưđ]{0,5}")
    matches = pattern.findall(text)
    if len(matches) < min_matches:
        return False

    density = len(matches) / max(1, len(text) / max(1, window_size))
    return density >= 0.8


def _apply_vni_digits(letter: str, digits: str) -> str:
    result = letter
    tone_mark = ""

    for digit in digits:
        if digit in _VNI_BASE_MODIFIERS and result in _VNI_BASE_MODIFIERS[digit]:
            # Unused branch kept for defensive compatibility.
            result = _VNI_BASE_MODIFIERS[digit][result]
            continue
        base_map = _VNI_BASE_MODIFIERS.get(result)
        if base_map and digit in base_map:
            result = base_map[digit]
        elif digit in _VNI_TONE_MARKS:
            tone_mark = _VNI_TONE_MARKS[digit]

    if tone_mark:
        result = unicodedata.normalize("NFC", unicodedata.normalize("NFD", result) + tone_mark)
    return result


def convert_vni_typing_to_unicode(text: str) -> str:
    """Convert VNI typed Vietnamese into NFC Unicode Vietnamese."""
    if not text:
        return text

    if not detect_vni_typing(text, min_matches=1):
        return normalize_vietnamese(text)

    converted: list[str] = []
    i = 0
    while i < len(text):
        char = text[i]
        if char.isalpha():
            j = i + 1
            while j < len(text) and text[j].isdigit():
                j += 1
            if j > i + 1:
                converted.append(_apply_vni_digits(char, text[i + 1:j]))
                i = j
                continue
        converted.append(char)
        i += 1

    return normalize_vietnamese("".join(converted))


def _convert_vni_token(token: str) -> str:
    """Convert a token that may contain VNI typing markers."""
    if not token or not re.search(r"[1-9]", token):
        return token
    return convert_vni_typing_to_unicode(token)


_TCVN3_CHAR_MAP = {
    "¸": "á",
    "µ": "à",
    "¶": "ả",
    "·": "ã",
    "¹": "ạ",
    "¨": "ă",
    "¾": "ắ",
    "»": "ằ",
    "¼": "ẳ",
    "½": "ẵ",
    "Æ": "ặ",
    "©": "â",
    "Ê": "ấ",
    "Ç": "ầ",
    "È": "ẩ",
    "É": "ẫ",
    "Ë": "ậ",
    "®": "đ",
    "Ð": "Đ",
    "¬": "ơ",
    "×": "ì",
    "ä": "ọ",
    "ö": "ộ",
}


def detect_broken_vn_font(text: str) -> bool:
    """Detect text likely encoded with broken Vietnamese legacy fonts (TCVN3/VNI artifacts)."""
    if not text:
        return False

    artifact_chars = set("¸µ¶·¹¨¾»¼½Æ©ÊÇÈÉË®Ð¬×äö□�")
    artifact_count = sum(1 for ch in text if ch in artifact_chars)
    if artifact_count >= 2:
        return True

    mojibake_patterns = [r"Ph\s*¬ng", r"tr×nh", r"bËc", r"To¸n", r"N¨m", r"học\s+and"]
    return any(re.search(pat, text) for pat in mojibake_patterns)


def fix_vietnamese_font_encoding(text: str) -> str:
    """Repair common Vietnamese encoding/font issues without external dependencies."""
    if not text:
        return text

    fixed = fix_vietnamese_text(text)

    if detect_vni_typing(fixed):
        fixed = convert_vni_typing_to_unicode(fixed)

    if detect_broken_vn_font(fixed):
        fixed = "".join(_TCVN3_CHAR_MAP.get(ch, ch) for ch in fixed)

    return normalize_vietnamese(fixed)


def fix_mojibake_topic(text: str) -> str:
    """Repair common UTF-8/Latin-1 mojibake often seen in topic titles."""
    if not text:
        return text

    fixed = str(text)
    for _ in range(2):
        if any(marker in fixed for marker in ("Ã", "Æ", "áº", "á»", "á»£")):
            try:
                candidate = fixed.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
            except Exception:
                break
            if candidate and candidate != fixed:
                fixed = candidate
                continue
        break
    return fix_vietnamese_font_encoding(fixed)


def fix_vietnamese_encoding(text: str) -> str:
    """Compatibility wrapper used by ingestion pipeline."""
    return fix_vietnamese_font_encoding(text)


def get_noto_sans_font_path() -> str:
    """Find a Noto Sans font that supports Vietnamese; return empty string if unavailable."""
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Medium.ttf",
        "/usr/share/fonts/opentype/noto/NotoSans-Regular.otf",
        "/usr/local/share/fonts/NotoSans-Regular.ttf",
        str(Path.home() / ".fonts" / "NotoSans-Regular.ttf"),
    ]

    for path in candidates:
        if Path(path).is_file():
            return path

    for root in ("/usr/share/fonts", "/usr/local/share/fonts", str(Path.home() / ".fonts")):
        root_path = Path(root)
        if not root_path.exists():
            continue
        for pattern in ("NotoSans*.ttf", "NotoSans*.otf"):
            for font_path in root_path.rglob(pattern):
                if "CJK" in font_path.name:
                    continue
                return str(font_path)

    return ""


def looks_garbled_short_title(text: str) -> bool:
    """Heuristic guard for short, likely broken Vietnamese titles."""
    s = str(text or "").strip()
    if not s or len(s) > 120:
        return False
    bad = sum(1 for ch in s if ch in "□�?")
    return bad > 0 or detect_broken_vn_font(s) or detect_vni_typing(s, min_matches=1)


def llm_repair_title_if_needed(text: str) -> str:
    """Optionally ask LLM to repair very short garbled titles."""
    title = str(text or "").strip()
    if not title or not looks_garbled_short_title(title):
        return title

    try:
        from app.services.llm_service import chat_text, llm_available
    except Exception:
        return title

    if not llm_available():
        return title

    prompt = (
        "Repair the following potentially garbled Vietnamese lesson title. "
        "Return only the repaired title, no explanation:\n" + title
    )
    repaired = (chat_text(prompt, temperature=0.0) or "").strip()
    return repaired or title


VIETNAMESE_DOCX_FONT = "Times New Roman"
VIETNAMESE_PDF_FONT = "Helvetica"
