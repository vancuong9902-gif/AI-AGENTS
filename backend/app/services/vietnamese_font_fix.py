from __future__ import annotations

import re
import unicodedata

# Common mojibake symbols that usually indicate legacy VnTime/TCVN3 text decoded incorrectly.
_ARTIFACT_CHARS = set("¸\u00ad¬×®¦§©")

# Sequence-level repairs first (multi-character mojibake patterns).
_SEQ_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("\u00ad¬", "ươ"),
    ("\u00ad", "ư"),
    ("¬", "ơ"),
    ("¦", "ư"),
)

# Character-level repairs for frequent TCVN3 symbols.
_CHAR_MAP: dict[str, str] = {
    "¸": "à",
    "µ": "á",
    "¶": "ả",
    "·": "ã",
    "¹": "ạ",
    "¨": "ă",
    "»": "ằ",
    "¾": "ắ",
    "¼": "ẳ",
    "½": "ẵ",
    "Æ": "ặ",
    "©": "â",
    "Ç": "ầ",
    "Ê": "ấ",
    "È": "ẩ",
    "É": "ẫ",
    "Ë": "ậ",
    "®": "đ",
    "Ì": "ề",
    "Ï": "ế",
    "Í": "ể",
    "Î": "ễ",
    "Ñ": "ệ",
    "ª": "ô",
    "Ò": "ồ",
    "Õ": "ố",
    "Ó": "ổ",
    "Ô": "ỗ",
    "Ö": "ộ",
    "×": "ờ",
    "Ø": "ớ",
    "Ü": "ở",
    "Ý": "ỡ",
    "Þ": "ợ",
    "Ý": "ỡ",
    "©": "â",
    "£": "ư",
    "§": "ă",
}


def detect_broken_vn_font(text: str) -> bool:
    s = str(text or "")
    if not s:
        return False

    if any(ch in _ARTIFACT_CHARS for ch in s):
        return True

    # High density of Latin-1 supplement often indicates bad decoding in Vietnamese docs.
    latin1_sup = sum(1 for ch in s if 0x00A0 <= ord(ch) <= 0x00FF)
    if latin1_sup / max(1, len(s)) > 0.08:
        return True

    return False


def fix_vietnamese_font_encoding(text: str) -> str:
    s = str(text or "")
    if not s:
        return s

    for src, dst in _SEQ_REPLACEMENTS:
        s = s.replace(src, dst)

    s = "".join(_CHAR_MAP.get(ch, ch) for ch in s)

    # Cleanup accidental duplicated spaces after replacements.
    s = re.sub(r"\s+", " ", s)
    return unicodedata.normalize("NFC", s)
