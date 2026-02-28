from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


# Heuristics tuned for Vietnamese/English educational PDFs.
# Goal: detect OCR-garbled content early so we don't generate "rác" questions.

_WORD_RX = re.compile(r"[A-Za-zÀ-ỹà-ỹ0-9]+", flags=re.UNICODE)
_SINGLE_LETTER_SEQ_RX = re.compile(r"\b(?:[A-Za-zÀ-ỹà-ỹ]\s+){4,}[A-Za-zÀ-ỹà-ỹ]\b")


def quality_score(text: str) -> float:
    """Return a 0..1 score where higher means cleaner natural language."""
    t = (text or "").strip()
    if not t:
        return 0.0

    total = len(t)
    if total < 40:
        # too short to be reliable
        return 0.15

    letters = sum(ch.isalpha() for ch in t)
    digits = sum(ch.isdigit() for ch in t)
    spaces = sum(ch.isspace() for ch in t)
    repl = t.count("�")

    # punctuation/symbol heavy -> likely code/math/garbled OCR
    symbols = sum(ch in "{}[]();:=<>/*+\\|`~^$#@" for ch in t)

    tokens = _WORD_RX.findall(t)
    tok_n = max(1, len(tokens))
    short_tok = sum(1 for w in tokens if len(w) <= 2)
    one_letter = sum(1 for w in tokens if len(w) == 1)

    # Ratios
    letter_ratio = letters / max(1, total)
    digit_ratio = digits / max(1, total)
    repl_ratio = repl / max(1, total)
    sym_ratio = symbols / max(1, total)
    short_ratio = short_tok / tok_n
    one_ratio = one_letter / tok_n

    # Base score from letter ratio (natural language tends to be 0.55+ for VN/EN)
    score = min(1.0, max(0.0, (letter_ratio - 0.25) / 0.55))

    # Penalize obvious OCR issues
    if repl_ratio > 0:
        score -= min(0.35, repl_ratio * 6.0)

    # Too many short tokens -> broken words like "vìˆy" / "có" split everywhere
    if short_ratio > 0.35:
        score -= min(0.35, (short_ratio - 0.35) * 1.1)

    # Spaced-letter PDFs: "t r ì n h" -> many 1-letter tokens and long sequences
    if one_ratio > 0.18:
        score -= min(0.4, (one_ratio - 0.18) * 1.7)
    if _SINGLE_LETTER_SEQ_RX.search(t):
        score -= 0.22

    # Symbol/code heavy
    if sym_ratio > 0.08:
        score -= min(0.25, (sym_ratio - 0.08) * 2.2)

    # Digit-heavy lines often come from page numbers / tables
    if digit_ratio > 0.22:
        score -= min(0.2, (digit_ratio - 0.22) * 1.2)

    # A little whitespace is expected; extremely low whitespace means joined words.
    if spaces / max(1, total) < 0.06:
        score -= 0.12

    return float(max(0.0, min(1.0, score)))


def quality_report(text: str) -> Dict[str, Any]:
    t = (text or "").strip()
    s = quality_score(t)
    reasons: List[str] = []
    if not t:
        reasons.append("empty")
    if "�" in t:
        reasons.append("replacement_char")
    if len(t) < 40:
        reasons.append("too_short")

    tokens = _WORD_RX.findall(t)
    if tokens:
        short_ratio = sum(1 for w in tokens if len(w) <= 2) / max(1, len(tokens))
        if short_ratio > 0.35:
            reasons.append("many_short_tokens")
        one_ratio = sum(1 for w in tokens if len(w) == 1) / max(1, len(tokens))
        if one_ratio > 0.18 or _SINGLE_LETTER_SEQ_RX.search(t):
            reasons.append("spaced_letters")

    # very naive: lots of non-letter characters
    letters = sum(ch.isalpha() for ch in t)
    if letters / max(1, len(t)) < 0.35:
        reasons.append("low_letter_ratio")

    return {"score": round(float(s), 4), "reasons": reasons}


def filter_chunks_by_quality(chunks: List[Dict[str, Any]], min_score: float) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    good: List[Dict[str, Any]] = []
    bad: List[Dict[str, Any]] = []
    for c in chunks or []:
        txt = str(c.get("text") or "")
        s = quality_score(txt)
        if s >= float(min_score):
            good.append(c)
        else:
            bad.append({**c, "_quality": quality_report(txt)})
    return good, bad
