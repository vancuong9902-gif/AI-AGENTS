from __future__ import annotations

import re
import unicodedata


# PDFs (especially some Vietnamese sources) sometimes use Eth-like glyphs for Đ/đ.
_ETH_FIX = {
    "Ð": "Đ",
    "ð": "đ",
}


def fix_eth_d(text: str) -> str:
    if not text:
        return ""
    for a, b in _ETH_FIX.items():
        if a in text:
            text = text.replace(a, b)
    return text


_VOWEL_BASE = set("aeiouyAEIOUY")


def _base_letter(ch: str) -> str:
    # Vietnamese diacritics: NFD splits base + combining marks.
    try:
        return unicodedata.normalize("NFD", ch)[0]
    except Exception:
        return ch


def _is_vowel_char(ch: str) -> bool:
    if not ch or not ch.isalpha():
        return False
    return _base_letter(ch) in _VOWEL_BASE


def _token_has_vowel_early(tok: str, limit: int = 3) -> bool:
    cnt = 0
    for ch in tok:
        if not ch.isalpha():
            continue
        cnt += 1
        if _is_vowel_char(ch):
            return True
        if cnt >= limit:
            break
    return False


def _token_ends_with_vowel(tok: str) -> bool:
    for ch in reversed(tok):
        if ch.isalpha():
            return _is_vowel_char(ch)
    return False


def _has_vn_diacritics(s: str) -> bool:
    return any(ch.isalpha() and ord(ch) > 127 for ch in (s or ""))


_CODE_HINT = re.compile(
    r"(>>>|\.py\b|\bimport\b|\bfrom\b|\bdef\b|\bclass\b|\breturn\b|Traceback|File \"<stdin>\"|NameError)",
    flags=re.IGNORECASE,
)


def _looks_like_math_or_code(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return False
    if _CODE_HINT.search(s):
        return True
    # If the line has many operators/digits and very few letters, treat as math-ish.
    if re.search(r"[0-9=+\-*/^<>]", s):
        letters = sum(1 for ch in s if ch.isalpha())
        ops = sum(1 for ch in s if ch in "=+-*/^<>")
        if ops >= 2 and letters <= 6:
            return True
        # ASCII-only with lots of symbols: likely code/config.
        if not _has_vn_diacritics(s) and ops >= 1 and letters <= 10:
            return True
    return False


def repair_ocr_spacing_line(line: str) -> str:
    """Repair common PDF/OCR word-splitting artifacts.

    Goal: improve readability without breaking code/math lines.
    Examples:
      - "Lập t rình" -> "Lập trình"
      - "điề u k hiể n" -> "điều khiển"
      - "Pytho n" -> "Python"
      - "phiê n bản" -> "phiên bản"
    """
    if not line:
        return ""

    s = fix_eth_d(line)
    raw = s.strip()
    if not raw:
        return raw
    if _looks_like_math_or_code(raw):
        return raw

    tokens = raw.split()
    if len(tokens) < 2:
        return raw

    # Split simple trailing punctuation so word-merge rules can work (e.g., "ật," -> "ật" ",").
    punct = {",", ".", ";", ":", "!", "?", ")", "]", "}"}
    expanded_p: list[str] = []
    for tok in tokens:
        if len(tok) >= 2 and tok[-1] in punct and tok[:-1].isalpha():
            expanded_p.append(tok[:-1])
            expanded_p.append(tok[-1])
        else:
            expanded_p.append(tok)
    tokens = expanded_p

    # 0) Split tokens like "nbản" -> "n" "bản" (helps "phiê nbản").
    coda_single = {"c", "m", "n", "p", "t"}
    expanded: list[str] = []
    for tok in tokens:
        if tok.isalpha() and len(tok) >= 3:
            first = tok[0].lower()
            if first in coda_single and _token_has_vowel_early(tok[1:], limit=3):
                # Avoid splitting digraph onsets like "ng", "nh", "ch".
                second = tok[1].lower()
                if (first, second) not in {("n", "g"), ("n", "h"), ("c", "h")}: 
                    expanded.append(tok[0])
                    expanded.append(tok[1:])
                    continue
        expanded.append(tok)
    tokens = expanded

    # 0.25) Fix boundary where the FIRST consonant of token B is actually the CODA of token A.
    # Example (common OCR glitch):
    #   "nhiệ mvụ" -> "nhiệm vụ"   (mvụ -> m + vụ, then coda merge)
    #   "thự chiện" -> "thực hiện" (move 'c' to previous: thự + c ; chiện -> hiện)
    # Heuristic: only shift when A looks like a short Vietnamese syllable fragment.
    coda_head = {"c", "m", "n", "p", "t"}
    head_fixed: list[str] = []
    i = 0
    while i < len(tokens):
        if i + 1 < len(tokens):
            a = tokens[i]
            b = tokens[i + 1]
            if (
                a.isalpha() and b.isalpha()
                and len(a) <= 4
                and _has_vn_diacritics(a)
                and _token_ends_with_vowel(a)
                and len(b) >= 3
                and b[0].lower() in coda_head
                and _token_has_vowel_early(b[1:], limit=3)
            ):
                # Avoid shifting when b clearly begins with a common onset digraph like "ng"/"nh".
                if not (b[0].lower() == "n" and b[1].lower() in {"g", "h"}):
                    a2 = a + b[0]
                    b2 = b[1:]
                    # Only accept if b2 still looks like a word (has a vowel soon).
                    if len(b2) >= 2 and _token_has_vowel_early(b2, limit=4):
                        head_fixed.append(a2)
                        tokens[i + 1] = b2
                        i += 1
                        continue
        head_fixed.append(tokens[i])
        i += 1
    tokens = head_fixed

    # 0.5) Fix boundary where the last consonant of a token is actually the onset of the next token.
    # Case A (next starts with a vowel): "máyt" + "ính" -> "máy" + "tính"
    # Case B (next starts with consonant that forms a valid onset cluster):
    #   "quyt" + "rình" -> "quy" + "trình"; "môit" + "rường" -> "môi" + "trường"
    onset_tail = set("tpkhrlvgdqsxc")
    onset_clusters = {"tr", "th", "ch", "ph", "ng", "nh", "kh", "gh", "gi", "qu"}
    # Small blocklist to avoid shifting in very common valid words ending with a consonant.
    _NO_SHIFT = {
        "một", "rất", "tất", "thật", "nhất", "kết", "tốt", "suất", "chất", "phát", "học",
        "luật", "lượt", "đặt", "viết", "biết", "cách",
    }
    shifted: list[str] = []
    i = 0
    while i < len(tokens):
        if i + 1 < len(tokens):
            a = tokens[i]
            b = tokens[i + 1]
            if (
                a.isalpha() and b.isalpha()
                and len(a) >= 3 and len(b) >= 2
                and a[-1].lower() in onset_tail
            ):
                al = a.lower()
                if al not in _NO_SHIFT:
                    first_alpha = next((ch for ch in b if ch.isalpha()), "")
                    # A) next starts with vowel
                    if first_alpha and _is_vowel_char(first_alpha):
                        a2 = a[:-1]
                        b2 = a[-1] + b
                        if len(a2) >= 2 and _token_has_vowel_early(a2, limit=3):
                            shifted.append(a2)
                            tokens[i + 1] = b2
                            i += 1
                            continue
                    # B) onset cluster shift (t + r -> tr; t + h -> th; ...)
                    if first_alpha and first_alpha.isalpha() and not _is_vowel_char(first_alpha):
                        cl = (a[-1] + first_alpha).lower()
                        if cl in onset_clusters:
                            a2 = a[:-1]
                            b2 = a[-1] + b
                            if len(a2) >= 2 and _token_has_vowel_early(a2, limit=3) and _token_has_vowel_early(b2, limit=4):
                                shifted.append(a2)
                                tokens[i + 1] = b2
                                i += 1
                                continue
        shifted.append(tokens[i])
        i += 1
    tokens = shifted

    # 1) Join long runs of tiny alphabetic tokens: "t h u ậ t" -> "thuật", "py t ho n" -> "python".
    out: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]

        if t.isalpha() and len(t) <= 3:
            j = i
            group: list[str] = []
            one_cnt = 0
            while j < len(tokens):
                tj = tokens[j]
                if tj.isalpha() and len(tj) <= 3:
                    group.append(tj)
                    if len(tj) == 1:
                        one_cnt += 1
                    j += 1
                    continue
                break

            total_chars = sum(len(x) for x in group)
            has_diac = any(_has_vn_diacritics(x) for x in group)
            vowel_tokens = sum(1 for x in group if _token_has_vowel_early(x, limit=3))
            # join if the run looks like a broken single *word* (NOT "word + broken next word").
            # For Vietnamese-diatrics groups, require more evidence (>=2 single-letter pieces)
            # so we don't join patterns like "Lập t rình" into "Lậptrình".
            if has_diac:
                # Special case: a single word spelled out by many tiny pieces
                # e.g., "ng u y ê n" -> "nguyên".
                onset_digraphs = {"ng", "nh", "ch", "th", "tr", "ph", "kh", "gi", "qu"}
                g0 = (group[0].lower() if group else "")
                starts_like_onset = (
                    (len(group[0]) == 1 and group[0].isalpha() and not _is_vowel_char(group[0]))
                    or (g0 in onset_digraphs)
                )
                if starts_like_onset and all(len(x) <= 2 for x in group) and one_cnt >= 2 and total_chars <= 10:
                    join_group = True
                # If there are many vowel-bearing tokens, it is likely multiple words.
                elif vowel_tokens >= 3:
                    join_group = False
                else:
                    join_group = (
                        (len(group) >= 4 and one_cnt >= 2) or
                        (len(group) >= 5 and one_cnt >= 3) or
                        (len(group) >= 6 and one_cnt >= 2)
                    )
            else:
                # ASCII-only groups (common in "py t ho n", URLs, etc.)
                if vowel_tokens >= 3 and one_cnt < 3:
                    join_group = False
                else:
                    join_group = (
                        (len(group) >= 4 and one_cnt >= 1) or
                        (len(group) >= 3 and one_cnt >= 1 and total_chars >= 6) or
                        (len(group) >= 5)
                    )
            if join_group:
                out.append("".join(group))
                i = j
                continue

        out.append(t)
        i += 1

    tokens = out

    # 2) Merge onset/coda patterns for Vietnamese.
    digraph_coda = {"ng", "nh", "ch"}
    res: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]

        # Look-ahead: single consonant onset "k" + "hiể" -> "khiể"
        if (
            t.isalpha() and len(t) == 1 and not _is_vowel_char(t)
            and i + 1 < len(tokens)
            and tokens[i + 1].isalpha() and len(tokens[i + 1]) >= 2
            and _token_has_vowel_early(tokens[i + 1], limit=3)
        ):
            # If the previous token ends with a vowel, this 1-letter consonant is likely a coda,
            # so do NOT treat it as an onset (avoid: "nghiê" + "n" + "cứu" -> "nghiê ncứu").
            if res and res[-1].isalpha() and len(res[-1]) >= 2 and _token_ends_with_vowel(res[-1]) and t.lower() in coda_single:
                pass
            else:
                res.append(t + tokens[i + 1])
                i += 2
                continue

        # Digraph onset: "th" + "u" + "ật" -> "thuật" (common in VN OCR)
        if (
            t.isalpha() and t.lower() in {"th", "tr", "ch", "ph", "ng", "nh", "kh", "gi", "qu"}
            and i + 2 < len(tokens)
            and tokens[i + 1].isalpha() and len(tokens[i + 1]) == 1 and _is_vowel_char(tokens[i + 1])
            and tokens[i + 2].isalpha() and len(tokens[i + 2]) >= 2 and _token_has_vowel_early(tokens[i + 2], limit=3)
        ):
            res.append(t + tokens[i + 1] + tokens[i + 2])
            i += 3
            continue

        # Two-consonant onset: "t" "h" "uật" -> "thuật"
        if (
            i + 2 < len(tokens)
            and tokens[i].isalpha() and len(tokens[i]) == 1 and not _is_vowel_char(tokens[i])
            and tokens[i + 1].isalpha() and len(tokens[i + 1]) == 1 and not _is_vowel_char(tokens[i + 1])
            and tokens[i + 2].isalpha() and len(tokens[i + 2]) >= 2
            and _token_has_vowel_early(tokens[i + 2], limit=3)
        ):
            res.append(tokens[i] + tokens[i + 1] + tokens[i + 2])
            i += 3
            continue

        if res:
            prev = res[-1]

            # coda merge: "phiê" + "n" -> "phiên"; "pytho" + "n" -> "python"
            if prev.isalpha() and len(prev) >= 2 and _token_ends_with_vowel(prev) and t.isalpha():
                tl = t.lower()
                if (len(t) == 1 and tl in coda_single) or (tl in digraph_coda):
                    res[-1] = prev + t
                    i += 1
                    continue

            # vowel tail split: "điề" + "u" -> "điều"
            if prev.isalpha() and t.isalpha() and len(t) == 1 and _is_vowel_char(t):
                if _has_vn_diacritics(prev) and _token_ends_with_vowel(prev):
                    res[-1] = prev + t
                    i += 1
                    continue

        res.append(t)
        i += 1

    fixed = " ".join(res)
    # Clean spacing around punctuation
    fixed = re.sub(r"\s+([,;:\.\?\!\)\]\}])", r"\1", fixed)
    fixed = re.sub(r"([\(\[\{])\s+", r"\1", fixed)

    # 3) Insert missing spaces after very common Vietnamese function words that are often glued in PDFs.
    # This is intentionally conservative (only a small list) to avoid harming technical text.
    fixed = re.sub(
        r"\b(một|các|những|trong|với|không|được|vì|nên|để)(?=[A-Za-zÀ-ỹà-ỹ])",
        r"\1 ",
        fixed,
        flags=re.IGNORECASE,
    )
    fixed = re.sub(r"\b(Python|NumPy|SciPy|Windows|Linux|macOS|IDLE)(?=[A-Za-zÀ-ỹà-ỹ])", r"\1 ", fixed)
    return fixed


def repair_ocr_spacing_text(text: str) -> str:
    if not text:
        return ""
    text = fix_eth_d(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    out = [repair_ocr_spacing_line(ln) for ln in lines]
    return "\n".join(out)
