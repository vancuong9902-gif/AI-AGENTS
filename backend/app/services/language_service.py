"""Language detection + preference utilities.

This project ingests documents that may not be Vietnamese.
We want MCQ + essay questions to follow the document language.

We keep this dependency-free (no heavy langdetect), using Unicode-script heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class Lang:
    code: str
    name: str
    confidence: float = 0.65

    def as_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "name": self.name, "confidence": float(self.confidence)}


_LANG_NAME = {
    "vi": "Vietnamese",
    "en": "English",
    "th": "Thai",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
    "ru": "Russian",
    "hi": "Hindi",
}


def _count_script_chars(text: str) -> Dict[str, int]:
    """Count rough Unicode script buckets (heuristic)."""

    counts = {
        "latin": 0,
        "vi": 0,
        "thai": 0,
        "cjk": 0,
        "hiragana_katakana": 0,
        "hangul": 0,
        "arabic": 0,
        "cyrillic": 0,
        "devanagari": 0,
    }

    for ch in text:
        o = ord(ch)
        if "a" <= ch.lower() <= "z":
            counts["latin"] += 1
            continue

        # Vietnamese-specific Latin extensions / tone marks
        if (
            0x0102 <= o <= 0x0103  # Ăă
            or 0x0110 <= o <= 0x0111  # Đđ
            or 0x0128 <= o <= 0x0129  # Ĩĩ
            or 0x0168 <= o <= 0x0169  # Ũũ
            or 0x01A0 <= o <= 0x01A1  # Ơơ
            or 0x01AF <= o <= 0x01B0  # Ưư
            or 0x1EA0 <= o <= 0x1EF9  # Vietnamese tone marks block
        ):
            counts["vi"] += 1
            continue

        # Thai
        if 0x0E00 <= o <= 0x0E7F:
            counts["thai"] += 1
            continue

        # CJK
        if 0x4E00 <= o <= 0x9FFF:
            counts["cjk"] += 1
            continue

        # Japanese Kana
        if (0x3040 <= o <= 0x309F) or (0x30A0 <= o <= 0x30FF):
            counts["hiragana_katakana"] += 1
            continue

        # Hangul
        if 0xAC00 <= o <= 0xD7AF:
            counts["hangul"] += 1
            continue

        # Arabic
        if 0x0600 <= o <= 0x06FF:
            counts["arabic"] += 1
            continue

        # Cyrillic
        if 0x0400 <= o <= 0x04FF:
            counts["cyrillic"] += 1
            continue

        # Devanagari
        if 0x0900 <= o <= 0x097F:
            counts["devanagari"] += 1
            continue

    return counts


def detect_language_heuristic(texts: Iterable[str] | str | None) -> Dict[str, Any]:
    """Return {code,name,confidence} based on Unicode script heuristics."""

    if texts is None:
        return Lang("vi", _LANG_NAME["vi"], 0.55).as_dict()

    if isinstance(texts, str):
        sample = texts
    else:
        buf: List[str] = []
        total = 0
        for t in texts:
            if not t:
                continue
            s = str(t)
            buf.append(s)
            total += len(s)
            if total >= 2500:
                break
        sample = "\n".join(buf)

    sample = (sample or "").strip()
    if not sample:
        return Lang("vi", _LANG_NAME["vi"], 0.55).as_dict()

    c = _count_script_chars(sample)

    # Strong script signals first
    if c["thai"] >= 8 and c["thai"] > c["latin"]:
        return Lang("th", _LANG_NAME["th"], 0.92).as_dict()
    if (c["hiragana_katakana"] >= 6) or (c["cjk"] >= 10 and c["hiragana_katakana"] >= 1):
        return Lang("ja", _LANG_NAME["ja"], 0.90).as_dict()
    if c["hangul"] >= 8:
        return Lang("ko", _LANG_NAME["ko"], 0.92).as_dict()
    if c["arabic"] >= 8:
        return Lang("ar", _LANG_NAME["ar"], 0.92).as_dict()
    if c["cyrillic"] >= 8:
        return Lang("ru", _LANG_NAME["ru"], 0.90).as_dict()
    if c["devanagari"] >= 8:
        return Lang("hi", _LANG_NAME["hi"], 0.90).as_dict()
    if c["cjk"] >= 12 and c["hiragana_katakana"] == 0:
        return Lang("zh", _LANG_NAME["zh"], 0.88).as_dict()

    # Vietnamese vs other Latin languages
    if c["vi"] >= 4:
        return Lang("vi", _LANG_NAME["vi"], 0.82).as_dict()

    # Default latin fallback
    return Lang("en", _LANG_NAME["en"], 0.62).as_dict()


def preferred_question_language(chunks: List[Dict[str, Any]] | None) -> Dict[str, Any]:
    """Infer output language from evidence chunks."""

    if not chunks:
        return Lang("vi", _LANG_NAME["vi"], 0.55).as_dict()

    texts: List[str] = []
    for c in (chunks or [])[:8]:
        if not isinstance(c, dict):
            continue
        t = c.get("text") or c.get("content") or ""
        if t:
            texts.append(str(t))

    return detect_language_heuristic(texts)
