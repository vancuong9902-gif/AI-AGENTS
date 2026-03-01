from __future__ import annotations

import re
import json
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from app.services.text_quality import quality_report, quality_score
from app.services.llm_service import llm_available, chat_json, chat_text
from app.services.external_sources import fetch_external_snippets
from app.core.config import settings
from app.services.text_repair import repair_ocr_spacing_line, repair_ocr_spacing_text
from app.services.vietnamese_font_fix import (
    detect_vni_typing,
    detect_broken_vn_font,
    convert_vni_typing_to_unicode,
    fix_mojibake_topic,
    fix_vietnamese_encoding,
    fix_vietnamese_font_encoding,
)


_WORD_RX = re.compile(r"[A-Za-zÀ-ỹà-ỹ0-9_]+", flags=re.UNICODE)


# "Auxiliary" section headings that should NEVER become standalone TOPIC titles.
# Users typically want these sections to live INSIDE the nearest learning topic.
_AUX_SECTION_RX = re.compile(
    r"^\s*(?:[\-•\*]+\s*)?(?:"
    # Practice / exercises
    r"bài\s*tập|bai\s*tap|luyện\s*tập|luyen\s*tap|tự\s*luyện|tu\s*luyen|"
    r"câu\s*hỏi|cau\s*hoi|practice|exercise|exercises|questions|question\s*bank|"
    r"mini\s*[- ]?quiz|quiz|"
    # Examples / worked examples (should live inside the nearest learning topic)
    r"ví\s*dụ|vi\s*du|example|examples|"
    # Answer keys / solutions
    r"đáp\s*án|dap\s*an|lời\s*giải|loi\s*giai|gợi\s*ý|goi\s*y|solution|solutions|answer\s*key|answers"
    r")\b",
    flags=re.IGNORECASE,
)



_PAGE_PREFIX_RX = re.compile(r"^\s*(?:trang|page|p\.?|pp\.?)\s*\d{1,4}\b", flags=re.IGNORECASE)
_NON_PRINTABLE_RX = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
_TOPIC_ALLOWED_CHARS_RX = re.compile(r"[^0-9A-Za-zÀ-ỹà-ỹ\s\-–—:;,.()/%&+\[\]'\"]", flags=re.UNICODE)
_TOPIC_PREFIX_RX = re.compile(
    r"^\s*(?:"
    r"\d{1,3}(?:\.\d{1,3}){0,4}\s*[\.)\]:\-–]?\s*"
    r"|(?:chương|chuong|chapter)\s+[0-9IVXLCDM]{1,6}\s*[:\-–]?\s*"
    r")",
    flags=re.IGNORECASE,
)



_GARBLED_TOPIC_PATTERNS = [
    re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]"),
    re.compile(r"[Ð¡¢£¤¥¦§¨©ª«¬®¯°±²³]"),
]


def validate_topic_title(title: str) -> str:
    """Đảm bảo topic title không chứa ký tự lỗi font."""
    cleaned = str(title or "").strip()
    if detect_vni_typing(cleaned):
        cleaned = convert_vni_typing_to_unicode(cleaned).strip()

    for pattern in _GARBLED_TOPIC_PATTERNS:
        if pattern.search(cleaned):
            fixed = fix_vietnamese_encoding(cleaned).strip()
            fixed = re.sub(r"[Ð¡¢£¤¥¦§¨©ª«¬®¯°±²³]", "", fixed).strip()
            score = quality_score(fixed)
            # Titles are short; quality_score is conservative on short text.
            readable_words = len(re.findall(r"[A-Za-zÀ-ỹà-ỹ]{2,}", fixed))
            if score > 0.6 or readable_words >= 3:
                return fixed
            raise ValueError(f"Topic title appears garbled: {cleaned[:50]}")
    return cleaned


def clean_topic_title(title: str) -> str:
    original = str(title or "").strip()
    cleaned = fix_mojibake_topic(original)

    repaired = repair_ocr_spacing_text(cleaned)
    # Titles are short; OCR spacing repair can over-split valid words.
    # Apply only when source title has no spaces and repair introduces readable tokenization.
    if cleaned.count(" ") == 0 and repaired.count(" ") >= 1 and quality_score(repaired) >= quality_score(cleaned):
        cleaned = repaired

    cleaned = _TOPIC_ALLOWED_CHARS_RX.sub(" ", cleaned)
    cleaned = _TOPIC_PREFIX_RX.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–—:;,.\t\n\r")
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]

    if len(cleaned) < 3:
        raise ValueError("Topic title quá ngắn sau khi clean")
    return cleaned


def extract_topics_from_headings(all_chunks: Optional[List[str]]) -> List[Dict[str, Any]]:
    """Fallback topic extraction from chunk headings when LLM output is not reliable."""
    if not all_chunks:
        return []
    return _extract_by_headings_in_chunks(all_chunks)


def post_process_generated_topics(raw_topics: List[Dict[str, Any]], all_chunks: Optional[List[str]]) -> List[Dict[str, Any]]:
    processed: List[Dict[str, Any]] = []
    chunks = all_chunks or []

    for topic in raw_topics:
        if not isinstance(topic, dict):
            continue
        title = fix_mojibake_topic(str(topic.get('title') or '').strip())
        if detect_broken_vn_font(title):
            title = fix_vietnamese_font_encoding(title)
        title = unicodedata.normalize("NFC", title)

        summary = fix_mojibake_topic(str(topic.get('summary') or topic.get('body') or '').strip())
        if detect_broken_vn_font(summary):
            summary = fix_vietnamese_font_encoding(summary)
        summary = unicodedata.normalize("NFC", summary)
        keywords_raw = topic.get('keywords') if isinstance(topic.get('keywords'), list) else []
        keywords = [str(x).strip().lower() for x in keywords_raw if str(x).strip()][:10]
        if not title or not keywords:
            continue
        try:
            cleaned_title = clean_topic_title(title)
        except ValueError:
            continue

        matching_chunks = [
            c for c in chunks
            if any(kw.lower() in str(c or '').lower() for kw in keywords)
        ]
        processed.append({
            'title': cleaned_title[:255],
            'body': summary or cleaned_title,
            '_llm': True,
            'keywords': keywords,
            'chunk_count': len(matching_chunks),
            'is_valid': len(matching_chunks) >= 2,
        })

    valid_topics = [t for t in processed if t.get('is_valid')]
    if len(valid_topics) < 1:
        return extract_topics_from_headings(chunks)
    return valid_topics


def validate_and_clean_topic_title(raw_title: str) -> tuple[str, list[str]]:
    """Clean and validate extracted topic title for UI display."""
    warnings: list[str] = []
    title = str(raw_title or "").strip()

    if not title:
        return "", ["empty_title", "needs_review=True"]

    try:
        validated = validate_topic_title(title)
        if validated != title:
            warnings.append("font_fixed")
            title = validated
    except ValueError:
        return "", ["garbled_title", "needs_review=True"]

    if detect_broken_vn_font(title):
        fixed = fix_vietnamese_font_encoding(title).strip()
        if fixed != title:
            warnings.append("font_fixed")
            title = fixed

    if _NON_PRINTABLE_RX.search(title):
        warnings.append("contains_control_chars")
        title = _NON_PRINTABLE_RX.sub("", title).strip()

    suspect_chars = "¸­¬×®¦§"
    if any(ch in title for ch in suspect_chars):
        warnings.append("contains_suspect_chars")
        title = "".join(ch for ch in title if ch not in suspect_chars).strip()

    if "□" in title:
        warnings.append("contains_tofu")
    if "�" in title:
        warnings.append("contains_replacement_char")

    if _PAGE_PREFIX_RX.match(title):
        warnings.append("starts_with_page_prefix")
    if _AUX_SECTION_RX.match(title):
        warnings.append("starts_with_aux_section")

    tlen = len(title)
    if tlen < 5 or tlen > 150:
        warnings.append("length_out_of_range")

    if detect_broken_vn_font(title) or any(x in title for x in ("□", "�")):
        warnings.append("needs_review=True")

    return title, warnings

# Minimal VN/EN stopword set for keyword extraction (kept small + stable).
_STOP = {
    "và",
    "là",
    "của",
    "cho",
    "trong",
    "một",
    "các",
    "được",
    "với",
    "khi",
    "này",
    "đó",
    "từ",
    "đến",
    "như",
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "are",
    "is",
    "to",
    "in",
    "on",
    "of",
    "a",
    "an",
    "be",
    "by",
    "as",
    "at",
    "or",
    "it",
    # generic education tokens
    "bài",
    "chương",
    "phần",
    "mục",
    "lesson",
    "chapter",
    "section",
    "unit",
    # meta/UI tokens
    "tài",
    "liệu",
    "dữ",
    "hệ",
    "thống",
    "test",
    "testing",
    "learning",
    "keyword",
    "keywords",
    "topic",
    "chunk",
    "range",
    "outline",
    "preview",
    "phiên",
    "bản",
    "ngôn",
    "mục",
    "đích",
    "xem",
    "chi",
    "tiết",
}


# NOTE:
# Do NOT treat generic words like "mục"/"bài" as headings by themselves.
# In textbook PDFs, headings nearly always include an index (e.g., "Chương 3", "Mục 10.9.8").
# The old regex was too permissive and caused false headings for normal sentences like
# "Mục tiêu ..." or "Bài toán ..." when chunk boundaries split mid-sentence.
_HEADING_HINT = re.compile(
    # Optional leading bullets + optional enumeration like "1." / "2)" / "I." before the label.
    r"^(\s*(?:[\-•\*]+\s*)?(?:(?:\d{1,2}(?:\.\d{1,3}){0,4}|[IVXLCDM]{1,8})\s*[\)\.\:\-–]\s*)?)"
    r"(chương|chuong|chapter|unit|lesson)\s+(?:[0-9]{1,3}|[IVXLCDM]{1,6})\b"
    r"|^(\s*(?:[\-•\*]+\s*)?(?:(?:\d{1,2}(?:\.\d{1,3}){0,4}|[IVXLCDM]{1,8})\s*[\)\.\:\-–]\s*)?)"
    r"(bài|bai|phần|phan|mục|muc|section)\s+(?:[0-9]{1,3}(?:\.[0-9]{1,3}){0,3}|[IVXLCDM]{1,6})\b"
    r"|^(\s*(?:[\-•\*]+\s*)?(?:(?:\d{1,2}(?:\.\d{1,3}){0,4}|[IVXLCDM]{1,8})\s*[\)\.\:\-–]\s*)?)"
    r"(chủ\s*đề|chu\s*de|topic)\s*[:\-–]\s+\S+"
    r"|^(\s*(?:[\-•\*]+\s*)?(?:(?:\d{1,2}(?:\.\d{1,3}){0,4}|[IVXLCDM]{1,8})\s*[\)\.\:\-–]\s*)?)"
    r"(phụ\s*lục|phu\s*luc|appendix)\s*(?:[:\-–]|—)\s+\S+"
    r"|^(\s*(?:[\-•\*]+\s*)?(?:(?:\d{1,2}(?:\.\d{1,3}){0,4}|[IVXLCDM]{1,8})\s*[\)\.\:\-–]\s*)?)"
    r"(giới\s*thiệu|gioi\s*thieu|introduction)\b\s*$"
    r"|^(\s*(?:[\-•\*]+\s*)?(?:(?:\d{1,2}(?:\.\d{1,3}){0,4}|[IVXLCDM]{1,8})\s*[\)\.\:\-–]\s*)?)"
    r"(phần|phan)\s+[\"“”'`].+[\"“”'`]\s*(?:\(.+\))?\s*$",
    flags=re.IGNORECASE,
)
_NUM_HEADING = re.compile(r"^\s*([\-•\*]+\s*)?(\d{1,2}(?:\.\d{1,3}){0,3})\s*([\)\.:\-–])?\s+\S+", flags=re.UNICODE)
_ROMAN_HEADING = re.compile(r"^\s*([\-•\*]+\s*)?([IVXLCDM]{1,6})\.?\s+\S+", flags=re.UNICODE)


def _split_evidence_units(full_text: str, chunks_texts: Optional[List[str]]) -> List[str]:
    """Build evidence units used for topic validation/scoring.

    Prefer chunk texts (already aligned with PDF chunks). Fallback to paragraphs.
    """
    if chunks_texts:
        units = [re.sub(r"\s+", " ", str(c or "")).strip() for c in chunks_texts]
        return [u for u in units if len(u) >= 40]

    blocks = re.split(r"\n\s*\n+", str(full_text or ""))
    units = [re.sub(r"\s+", " ", b).strip() for b in blocks]
    return [u for u in units if len(u) >= 40]


def _topic_tokens(text: str) -> List[str]:
    toks = [w.lower() for w in (_WORD_RX.findall(text or "") or [])]
    return [t for t in toks if len(t) >= 3 and t not in _STOP]


def _unit_mentions_topic(topic: Dict[str, Any], unit: str) -> bool:
    unit_norm = re.sub(r"\s+", " ", str(unit or "")).strip().lower()
    if not unit_norm:
        return False

    title = str(topic.get("title") or "").strip().lower()
    if title and title in unit_norm:
        return True

    # Match on meaningful token overlap.
    u_tokens = set(_topic_tokens(unit_norm))
    t_tokens = _topic_tokens(title)
    if t_tokens and len(u_tokens.intersection(t_tokens)) >= min(2, len(set(t_tokens))):
        return True

    for kw in (topic.get("keywords") or [])[:12]:
        kw_norm = re.sub(r"\s+", " ", str(kw or "")).strip().lower()
        if not kw_norm:
            continue
        if kw_norm in unit_norm:
            return True
        kw_tokens = [x for x in _topic_tokens(kw_norm) if x not in _STOP]
        if kw_tokens and len(u_tokens.intersection(kw_tokens)) >= min(2, len(set(kw_tokens))):
            return True
    return False


def _derive_subtopics(topic: Dict[str, Any]) -> List[str]:
    raw = topic.get("outline") if isinstance(topic.get("outline"), list) else []
    out: List[str] = []
    for x in raw:
        s = re.sub(r"\s+", " ", str(x or "")).strip(" -•\t\n\r")
        if not s:
            continue
        if len(s) < 4 or len(s) > 120:
            continue
        if s.lower() == str(topic.get("title") or "").strip().lower():
            continue
        if s not in out:
            out.append(s)
        if len(out) >= 6:
            break
    if out:
        return out

    for kw in (topic.get("keywords") or [])[:6]:
        s = re.sub(r"\s+", " ", str(kw or "")).strip()
        if not s:
            continue
        s2 = s[:1].upper() + s[1:]
        if s2 not in out and len(s2) >= 4:
            out.append(s2)
        if len(out) >= 3:
            break
    return out


# ===== Chapter-only heading detection (for textbook PDFs) =====
_CHAPTER_ONLY_RX = re.compile(
    # Accept both: "Chương 2: ..." and "Chương 2 ..." (many PDFs omit ':' after OCR).
    r"^\s*(?:[\-•\*]+\s*)?(?:chương|chuong|chapter)\s+(?:\d{1,3}|[IVXLCDM]{1,6})\b(?:\s*(?:[:\-–—\.]\s*)?\s+.*)?$",
    flags=re.IGNORECASE,
)
_TOPLEVEL_SECTIONS_RX = re.compile(
    r"^\s*(?:mở\s*đầu|mo\s*dau|giới\s*thiệu|gioi\s*thieu|lời\s*nói\s*đầu|loi\s*noi\s*dau|"
    r"kết\s*luận|ket\s*luan|tài\s*liệu\s*tham\s*khảo|tai\s*lieu\s*tham\s*khao|phụ\s*lục|phu\s*luc|appendix)\b.*$",
    flags=re.IGNORECASE,
)


def _extract_by_chapters(full_text: str) -> List[Dict[str, Any]]:
    """Split document into topics strictly by CHƯƠNG/CHAPTER headings (+ top-level sections)."""
    raw = [ln for ln in (full_text or "").replace("\r", "").split("\n")]
    lines = [_clean_line(ln) for ln in raw]
    if not any(ln.strip() for ln in lines):
        return []

    toc_map = {}
    try:
        toc_map = _parse_toc_title_map(raw, lines)
    except Exception:
        toc_map = {}

    idxs: List[int] = []
    seen_titles: set[str] = set()
    in_toc = False
    toc_lines = 0
    TOC_MAX_LINES = 260
    for i, ln in enumerate(lines):
        if not ln:
            continue
        if _TOC_START_RX.match(ln):
            in_toc = True
            toc_lines = 0
            continue
        if in_toc:
            toc_lines += 1
            if _TOC_END_RX.match(ln) or toc_lines >= TOC_MAX_LINES:
                in_toc = False
                continue
            # skip TOC lines
            continue

        if _CHAPTER_ONLY_RX.match(ln) or _TOPLEVEL_SECTIONS_RX.match(ln):
            # De-dup repeated page headers like "Chương 5 ..." appearing on every page.
            key = re.sub(r"\s+", " ", ln.strip().lower())
            if key in seen_titles:
                continue
            seen_titles.add(key)
            idxs.append(i)

    if not idxs:
        # Fallback: infer "chapters" from numbered subsections like 1.1, 2.3 ...
        num_rx = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\b")
        firsts = []
        seen = set()
        for i, ln in enumerate(lines):
            m = num_rx.match(ln or '')
            if not m:
                continue
            n = int(m.group(1))
            if n in seen:
                continue
            seen.add(n)
            firsts.append((i, n, ln))
        if not firsts:
            return []
        idxs = [i for i, _, _ in firsts]
        # Build pseudo chapter titles: "Chương N - <first subsection heading>"
        pseudo_titles = {i: f"Chương {n} - {(_clean_line(ln) or '').strip()}"[:255] for i, n, ln in firsts}
        # Store for later use when creating topics
        _pseudo_title_map = pseudo_titles
    else:
        _pseudo_title_map = {}

    # de-dup near-duplicates
    idxs2: List[int] = []
    for i in idxs:
        if not idxs2 or i - idxs2[-1] > 1:
            idxs2.append(i)
    idxs = idxs2

    topics: List[Dict[str, Any]] = []
    for j, i in enumerate(idxs):
        raw_title = (_pseudo_title_map.get(i) if isinstance(_pseudo_title_map, dict) else None) or _clean_line(lines[i])

        # If this is a chapter heading, prefer TOC-derived titles (cleaner than OCR page headers).
        title = raw_title
        try:
            m = re.match(r"^\s*(?:chương|chuong|chapter)\s+(\d{1,3}|[IVXLCDM]{1,6})\b\s*(.*)$", raw_title, flags=re.IGNORECASE)
            if m:
                idx_raw = (m.group(1) or "").strip()
                rest = (m.group(2) or "").strip()
                n = int(idx_raw) if idx_raw.isdigit() else (_roman_to_int(idx_raw) or None)
                if n is not None and isinstance(toc_map, dict) and toc_map.get(n):
                    title = f"Chương {n} - {toc_map.get(n)}"[:255]
                elif rest:
                    cleaned_rest = rest.lstrip(":").strip()
                    title = f"Chương {idx_raw} - {cleaned_rest}"[:255]
        except Exception:
            title = raw_title

        # Normalize top-level section titles
        if _TOPLEVEL_SECTIONS_RX.match(raw_title or ''):
            # Keep the first token as title (e.g. 'MỞ ĐẦU', 'KẾT LUẬN')
            title = _clean_line(raw_title)[:255]
        start = i + 1
        end = idxs[j + 1] if j + 1 < len(idxs) else len(lines)
        body = "\n".join(raw[start:end]).strip()
        if len(re.sub(r"\s+", " ", body)) < 35:
            continue
        topics.append({"title": title, "body": body})
    return topics


def _extract_by_chapters_in_chunks(chunks_texts: List[str]) -> List[Dict[str, Any]]:
    """Chapter split fallback using chunk texts."""
    starts: List[Tuple[int, int, str]] = []
    seen_titles: set[str] = set()
    for ci, tx in enumerate(chunks_texts or []):
        if not tx:
            continue
        raw_lines = (tx or '').replace('\r', '').split('\n')
        for li, ln in enumerate(raw_lines):
            cl = _clean_line(ln)
            if not cl:
                continue
            if _CHAPTER_ONLY_RX.match(cl) or _TOPLEVEL_SECTIONS_RX.match(cl):
                key = re.sub(r"\s+", " ", cl.strip().lower())
                if key in seen_titles:
                    continue
                seen_titles.add(key)
                starts.append((int(ci), int(li), cl))

    if not starts:
        # Fallback: infer chapters from numbered subsections like 1.1, 2.1 ...
        num_rx = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\b")
        seen = set()
        for ci, tx in enumerate(chunks_texts or []):
            if not tx:
                continue
            for li, ln in enumerate((tx or '').replace('\r', '').split('\n')):
                cl = _clean_line(ln)
                m = num_rx.match(cl or '')
                if not m:
                    continue
                n = int(m.group(1))
                if n in seen:
                    continue
                seen.add(n)
                title = f"Chương {n} - {cl}"[:255]
                starts.append((int(ci), int(li), title))
        if not starts:
            return []

# keep first occurrence per chapter title
    seen = set()
    uniq: List[Tuple[int, int, str]] = []
    for ci, li, title in starts:
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append((ci, li, title))
    starts = uniq

    topics: List[Dict[str, Any]] = []
    for j, (start_ci, start_li, title) in enumerate(starts):
        if j + 1 < len(starts):
            next_ci, next_li, _ = starts[j + 1]
            end_ci = int(next_ci)
            end_li = int(next_li) - 1
        else:
            end_ci = int(len(chunks_texts) - 1)
            end_li = None

        body_parts: List[str] = []
        for ci in range(int(start_ci), int(end_ci) + 1):
            tx = chunks_texts[ci] or ''
            raw_lines = tx.replace('\r', '').split('\n')
            from_i = int(start_li) + 1 if ci == int(start_ci) else 0
            if ci == int(end_ci) and end_li is not None:
                to_i = max(from_i, int(end_li) + 1)
            else:
                to_i = len(raw_lines)
            seg = '\n'.join(raw_lines[from_i:to_i]).strip()
            if seg:
                body_parts.append(seg)

        body = '\n\n'.join(body_parts).strip()
        if len(re.sub(r'\s+', ' ', body)) < 35:
            continue
        topics.append({
            'title': title,
            'body': body,
            'start_chunk_index': int(start_ci),
            'end_chunk_index': int(end_ci),
        })

    return topics


# ===== Topic title rewrite (LLM) =====

_GENERIC_TITLE_RX = re.compile(
    r"^\s*(topic|chủ\s*đề|chu\s*de|phần|phan|mục|muc|bài|bai|chương|chuong|chapter|unit|lesson|section)\s*"
    r"([0-9]{1,3}|[IVXLCDM]{1,6})(?:\s*[:\-–].*)?$",
    flags=re.IGNORECASE,
)


def _topic_title_rewrite_enabled() -> bool:
    # Modes: off | auto | always
    mode = (getattr(settings, 'TOPIC_LLM_TITLES', 'auto') or 'auto').strip().lower()
    if mode == 'off':
        return False
    if mode == 'always':
        return True
    # auto
    return llm_available()


def _looks_like_keyword_list(title: str) -> bool:
    # Typical fallback: "Topic 1: kw1, kw2, kw3". Also catches titles that are mostly commas/keywords.
    s = _clean_line(title).lower()
    if s.startswith('topic') and (':' in s or s.count(',') >= 1):
        return True
    # Exception: physics shorthand like 'Mạch R, L, C nối tiếp' is a real title, not a keyword list.
    if ('mạch' in s or 'mach' in s) and (re.search(r'\br\s*,\s*l\s*,\s*c\b', s) or 'rlc' in s):
        return False

    # Too many commas -> likely just a list
    if s.count(',') >= 2 and len(s) <= 70:
        return True
    return False


def _is_generic_title(title: str) -> bool:
    s = _clean_line(title)
    if not s:
        return True

    sl = s.lower()
    # Explicit fallback patterns
    if sl.startswith('topic '):
        return True
    if sl.startswith('topic:') or sl.startswith('topic-'):
        return True
    if _looks_like_keyword_list(s):
        return True

    # "Chương 1" / "Phần II" etc without descriptive text
    m = _GENERIC_TITLE_RX.match(sl)
    if m:
        # If there is a ':' part, it might still be okay if descriptive, but keyword-list titles are handled above.
        # When no ':' and token count is very small -> generic.
        tok = _WORD_RX.findall(s)
        if len(tok) <= 3:
            return True

    # Very short headings: only treat as generic when they are clearly meta/aux headings.
    tok = _WORD_RX.findall(s)
    if len(tok) <= 2:
        meta = {
            'mục tiêu','muc tieu','khái niệm','khai niem','ý chính','y chinh',
            'tóm tắt','tom tat','kết luận','ket luan','tổng quan','tong quan',
            'bài tập','bai tap','luyện tập','luyen tap','đáp án','dap an','lời giải','loi giai',
        }
        if sl in meta or _AUX_SECTION_RX.match(s) or len(s) < 6:
            return True
        # allow short, meaningful scientific titles like 'Âm học', 'Phóng xạ'
        return False
    if len(s) < 6:
        return True

    return False


def _normalize_title_candidate(title: str) -> str:
    t = _clean_line(title)
    t = re.sub(r"^[\"\'`]+|[\"\'`]+$", "", t).strip()
    t = re.sub(r"\s+", " ", t).strip()
    # Remove leading generic prefixes if the model kept them
    t = re.sub(r"^(topic|chủ\s*đề|chu\s*de)\s*\d+\s*[:\-–]?\s*", "", t, flags=re.IGNORECASE).strip()
    # Cap length
    if len(t) > 110:
        t = t[:107].rstrip() + '…'
    return t



# ===== Topic title cleanup (remove chapter/section numbering) =====

_TITLE_PREFIX_RX = re.compile(
    r"^\s*(?:[\-•\*]+\s*)?(?:"
    r"(?:chương|chuong|chapter|unit|lesson)\s+(?:[0-9]{1,3}|[IVXLCDM]{1,6})"
    r"|(?:phần|phan|mục|muc|bài|bai|section)\s+(?:[0-9]{1,3}(?:\.[0-9]{1,3}){0,4}|[IVXLCDM]{1,6})"
    r"|(?:topic)\s*[0-9]{1,3}"
    r")\s*[\.\)\]:\-–]*\s*",
    flags=re.IGNORECASE,
)

_TITLE_ENUM_RX = re.compile(
    r"^\s*(?:[\-•\*]+\s*)?(?:"
    r"[0-9]{1,2}(?:\.[0-9]{1,3}){0,4}"
    r"|[IVXLCDM]{1,8}"
    r")\s*[\.\)\]:\-–]+\s+",
    flags=re.IGNORECASE,
)


_LABEL_PREFIX_RX = re.compile(r"^\s*(chủ\s*đề|chu\s*de|topic)\s*[:\-–]\s*(.+)$", flags=re.IGNORECASE)
_APPENDIX_PREFIX_RX = re.compile(r"^\s*(phụ\s*lục|phu\s*luc|appendix)\s*(?:[:\-–]|—)\s*(.+)$", flags=re.IGNORECASE)

# "Soft" subject headings in many teacher notes / synthetic TXT docs.
# These headings often do NOT include numeric indices (Chương/Mục/...) and do not use "Chủ đề:".
# Example:
#   "Hóa học (Cơ bản – Phản ứng – Dung dịch)"  -> followed by "Ít dữ liệu" / "Ý chính" / "Khái niệm".
_SOFT_HEADING_MARKERS = {
    'ít dữ liệu', 'it du lieu',
    'ý chính', 'y chinh',
    'khái niệm', 'khai niem',
    'mục tiêu', 'muc tieu',
    'quiz-ready',
}

_SOFT_SUBJECT_HINTS = [
    # Common Vietnamese school subject / section keywords.
    'toán', 'đại số', 'giải tích',
    'vật lý', 'cơ học', 'điện học', 'nhiệt học',
    'hóa', 'hóa học', 'phản ứng', 'dung dịch',
    'sinh', 'sinh học', 'tế bào', 'di truyền', 'sinh thái',
    'tin', 'tin học', 'thuật toán', 'dữ liệu', 'an toàn thông tin',
    'xác suất', 'thống kê',
    'kinh tế', 'cung', 'cầu', 'lạm phát', 'lãi suất',
    'địa lý', 'khí hậu', 'dân số', 'tài nguyên',
    'lịch sử', 'bối cảnh', 'nguyên nhân', 'hệ quả',
    'đọc hiểu', 'viết', 'ngữ văn',
    'kỹ năng', 'học tập', 'ghi nhớ',
]


def is_appendix_title(title: str) -> bool:
    """Return True if a title looks like an appendix header (Phụ lục / Appendix)."""
    t = _clean_line(title or '').lower()
    if not t:
        return False
    if t.startswith('phụ lục') or t.startswith('phu luc') or t.startswith('appendix'):
        return True
    # Also treat answer-keys / end-of-book practice sections as appendix-like.
    # This prevents "ĐÁP ÁN" / "MINI-QUIZ" blocks from leaking into topic previews and quiz evidence.
    if t.startswith('đáp án') or t.startswith('dap an') or t.startswith('answer key') or t.startswith('answers'):
        return True
    if 'mini-quiz' in t or 'mini quiz' in t or t.startswith('quiz'):
        return True
    if t.startswith('bảng công thức') or t.startswith('bang cong thuc'):
        return True
    if t.startswith('các lỗi sai') or t.startswith('cac loi sai'):
        return True
    return bool(_APPENDIX_PREFIX_RX.match(title or ''))


def _next_non_empty(cleaned_lines: List[str], i: int, *, max_ahead: int = 3) -> str | None:
    if not cleaned_lines:
        return None
    n = len(cleaned_lines)
    for j in range(i + 1, min(n, i + 1 + int(max_ahead))):
        s = cleaned_lines[j]
        if s and s.strip():
            return s
    return None


def _is_soft_topic_heading(line: str, cleaned_lines: List[str], i: int) -> bool:
    """Heuristic heading detector for docs without explicit "Chủ đề:" labels.

    We only accept a line as a topic heading if it *looks* like a title AND
    it is followed by a known marker line ("Ít dữ liệu", "Ý chính", "Khái niệm", ...).
    This avoids splitting on ordinary sentences.
    """
    s = _clean_line(line)
    if not s:
        return False
    if _looks_like_question_item(s):
        return False
    if _is_bad_heading_candidate(s):
        return False

    # Titles should not end with sentence punctuation.
    if re.search(r"[\.!?;]$", s.strip()):
        return False
    if ':' in s or '：' in s:
        return False

    # Token length guard
    toks = _WORD_RX.findall(s)
    if len(toks) < 2 or len(toks) > 16:
        return False
    if len(s) < 8 or len(s) > 95:
        return False

    sl = s.lower()
    has_title_shape = (
        ('(' in s and ')' in s)
        or ('–' in s)
        or ('—' in s)
        or (' - ' in s)
        or any(h in sl for h in _SOFT_SUBJECT_HINTS)
    )
    if not has_title_shape:
        return False

    nxt = _next_non_empty(cleaned_lines, i, max_ahead=3)
    if not nxt:
        return False
    nl = _clean_line(nxt).lower()
    if not nl:
        return False
    # Marker line or a bullet-heavy line right after the title is a strong sign.
    if any(nl.startswith(m) for m in _SOFT_HEADING_MARKERS):
        return True
    if nl.startswith('•') or nl.startswith('-') or nl.startswith('*'):
        return True
    return False


def _strip_topic_numbering(title: str) -> str:
    """Remove leading 'Chương 12', 'Mục 10.9.8', '1.2.3' ... from a title.

    Returns '' when stripping would remove almost all meaningful content.
    """
    t = _clean_line(title)
    if not t:
        return ""

    t2 = _TITLE_PREFIX_RX.sub("", t)
    t2 = _TITLE_ENUM_RX.sub("", t2)
    t2 = re.sub(r"^\s*[:\-–\.\)\]]+\s*", "", t2).strip()
    t2 = re.sub(r"\s+", " ", t2).strip()

    # If we removed something but the remaining is too short, treat as non-meaningful.
    if t2 != t:
        tok = _WORD_RX.findall(t2)
        if len(tok) < 2 or len(t2) < 6:
            return ""
    return t2


def _strip_label_prefix(title: str) -> str:
    """Remove label prefixes like "Chủ đề:" / "Topic:" while keeping meaning.

    We keep "Phụ lục" as a meaningful category marker.
    """
    t = _clean_line(title)
    if not t:
        return ''
    m = _APPENDIX_PREFIX_RX.match(t)
    if m:
        rest = _clean_line(m.group(2))
        return f"Phụ lục — {rest}" if rest else "Phụ lục"
    m2 = _LABEL_PREFIX_RX.match(t)
    if m2:
        rest = _clean_line(m2.group(2))
        return rest
    return t


def _clean_topic_body(body: str, *, window: int = 30) -> str:
    """Light, safe de-noising for display + summarization.

    - Drop standalone structural markers (Quiz-ready/Ý chính/Khái niệm/...)
    - De-dup repeated lines within a small moving window
    - Keep everything else verbatim (no hallucination)
    """
    if not body:
        return ''
    try:
        body = repair_ocr_spacing_text(body or '')
    except Exception:
        body = body or ''
    raw_lines = [ln.rstrip() for ln in (body or '').replace('\r', '').split('\n')]
    drop_exact = {
        'quiz-ready',
        'ý chính',
        'y chinh',
        'khái niệm',
        'khai niem',
        'mục tiêu',
        'muc tieu',
        'ý chính (',
    }

    out: list[str] = []
    recent: list[str] = []

    for ln in raw_lines:
        ln_rep = repair_ocr_spacing_line(ln) if ln else ln
        cl = _clean_line(ln_rep)
        if not cl:
            # keep paragraph breaks lightly
            if out and out[-1] != '':
                out.append('')
            continue
        key = cl.lower()
        if key in drop_exact:
            continue
        if key.startswith('ngôn ngữ:') or key.startswith('mục đích:'):
            # meta lines: helpful once, but often repeated
            if any(x.startswith(key.split(':', 1)[0]) for x in recent):
                continue

        # De-dup within a moving window
        if key in recent:
            continue
        out.append((ln_rep or ln).strip())
        recent.append(key)
        if len(recent) > int(window):
            recent.pop(0)

    # strip trailing blank lines
    while out and out[-1] == '':
        out.pop()
    # collapse multiple blank lines
    cleaned: list[str] = []
    for ln in out:
        if ln == '' and cleaned and cleaned[-1] == '':
            continue
        cleaned.append(ln)
    return '\n'.join(cleaned).strip()


def clean_topic_text_for_display(text: str) -> str:
    """Public helper used by API routes/UI previews.

    We keep it deterministic and *non-destructive* (only drops obvious UI markers and
    repeated lines). This prevents users from seeing noisy markers like 'Quiz-ready' and
    reduces duplicated paragraphs in topic previews.
    """
    # 1) Deterministic cleanup (drop UI markers, repeated lines)
    cleaned = _clean_topic_body(text or '')
    # 2) Conservative unglue pass for very common Vietnamese collocations
    #    (improves readability of many PDFs with missing spaces)
    return _normalize_vn_pairs(cleaned)


# ===== Practice / answer-key separation =====

_MCQ_CHOICES_RX = re.compile(r"\bA\.\s+.+\bB\.\s+.+\bC\.\s+.+\bD\.\s+.+", flags=re.UNICODE)


def _is_mcq_choices_line(line: str) -> bool:
    s = _clean_line(line)
    if not s:
        return False
    # A. ... B. ... C. ... D. ... in one line
    if _MCQ_CHOICES_RX.search(s):
        return True
    # Multi-line choices (single choice line)
    if re.match(r"^[A-D]\.[\)\]]?\s+\S+", s.strip()):
        return True
    return False


def _is_answer_key_line(line: str) -> bool:
    s = _clean_line(line).lower()
    if not s:
        return False
    if s.startswith('đáp án') or s.startswith('dap an'):
        return True
    if s.startswith('answer') or s.startswith('answers') or s.startswith('answer key'):
        return True
    # common in synthetic docs
    if s.startswith('đáp án:') or s.startswith('dap an:'):
        return True
    return False


def _is_practice_marker_line(line: str) -> bool:
    s = _clean_line(line).lower()
    if not s:
        return False
    markers = (
        'bài tập', 'bai tap', 'luyện tập', 'luyen tap',
        'câu hỏi', 'cau hoi', 'trắc nghiệm', 'trac nghiem',
        'tự luận', 'tu luan', 'mini-quiz', 'mini quiz',
        'quiz',
    )
    return any(m in s for m in markers)


def split_study_and_practice(text: str) -> tuple[str, str]:
    """Split a topic text into (study_text, practice_text).

    This is designed to fix user-visible noise where question blocks (Q11, A/B/C/D choices, đáp án)
    leak into topic previews and key points.

    It is intentionally conservative:
    - Only moves lines that look like exercises/questions/answers.
    - Keeps the rest intact.
    """
    if not text:
        return ("", "")
    raw_lines = [ln.rstrip() for ln in (text or '').replace('\r', '').split('\n')]
    study: list[str] = []
    prac: list[str] = []
    mode = 'study'

    def _append(buf: list[str], ln: str) -> None:
        if not ln.strip():
            if buf and buf[-1] != '':
                buf.append('')
            return
        buf.append(ln.strip())

    for ln in raw_lines:
        cl = _clean_line(ln)

        # Keep spacing
        if not cl:
            _append(prac if mode == 'practice' else study, '')
            continue

        # Switch to practice on strong signals
        if _is_answer_key_line(cl) or _is_mcq_choices_line(cl) or _looks_like_question_item(cl) or _is_practice_marker_line(cl):
            mode = 'practice'

        # Allow switching back when a new non-practice heading appears (rare, but helps mixed docs)
        if mode == 'practice' and _is_heading(cl) and not (_is_answer_key_line(cl) or _is_practice_marker_line(cl)):
            mode = 'study'

        _append(prac if mode == 'practice' else study, ln)

    # Trim
    def _finalize(buf: list[str]) -> str:
        while buf and buf[-1] == '':
            buf.pop()
        out: list[str] = []
        for x in buf:
            if x == '' and out and out[-1] == '':
                continue
            out.append(x)
        return "\n".join(out).strip()

    return (_finalize(study), _finalize(prac))


def clean_text_for_generation(text: str) -> str:
    """Remove obvious practice/answer-key lines from evidence text before question generation.

    We do NOT delete normal bullet lists or definitions.
    """
    if not text:
        return ''
    try:
        text = repair_ocr_spacing_text(text)
    except Exception:
        pass
    raw_lines = [ln.rstrip() for ln in (text or '').replace('\r', '').split('\n')]
    out: list[str] = []
    for ln in raw_lines:
        ln_rep = repair_ocr_spacing_line(ln) if ln else ln
        cl = _clean_line(ln_rep)
        if not cl:
            if out and out[-1] != '':
                out.append('')
            continue
        if _is_answer_key_line(cl) or _is_mcq_choices_line(cl) or _looks_like_question_item(cl):
            continue
        # Drop standalone UI markers that sometimes remain in chunks
        if cl.lower() in {'quiz-ready', 'ít dữ liệu', 'it du lieu', 'ý chính', 'y chinh', 'khái niệm', 'khai niem'}:
            continue
        out.append((ln_rep or ln).strip())
    return "\n".join(out).strip()


def _title_token_set(title: str) -> set[str]:
    s = _clean_line(title).lower()
    toks = [t for t in _WORD_RX.findall(s) if len(t) >= 3 and t not in _STOP and not t.isdigit()]
    return set(toks)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return float(inter) / float(max(1, union))


def _merge_similar_topics(topics: List[Dict[str, Any]], *, max_topics: int) -> List[Dict[str, Any]]:
    """Merge near-duplicate topics produced by noisy outlines.

    Strategy (deterministic):
    - If title token Jaccard >= 0.75 OR keyword overlap >= 0.65 -> merge
    - When merging: concat bodies, union keywords, expand chunk ranges (min start, max end)
    """
    if not topics:
        return []

    merged: list[dict[str, Any]] = []

    for t in topics:
        title = str(t.get('title') or '').strip()
        body = str(t.get('body') or '').strip()
        if not title or not body:
            continue
        toks = _title_token_set(title)
        kws = set([str(x).strip().lower() for x in (t.get('keywords') or []) if str(x).strip()])

        best_i = None
        best_score = 0.0
        for i, m in enumerate(merged):
            mtoks = _title_token_set(str(m.get('title') or ''))
            mkws = set([str(x).strip().lower() for x in (m.get('keywords') or []) if str(x).strip()])
            score = max(_jaccard(toks, mtoks), _jaccard(kws, mkws))
            if score > best_score:
                best_score = score
                best_i = i

        if best_i is not None and best_score >= 0.75:
            m = merged[int(best_i)]
            # merge bodies with separator (keep both)
            m['body'] = (str(m.get('body') or '').rstrip() + "\n\n" + body).strip()
            # merge keywords
            mkws = [str(x).strip().lower() for x in (m.get('keywords') or []) if str(x).strip()]
            for x in kws:
                if x not in mkws:
                    mkws.append(x)
            m['keywords'] = mkws[:16]
            # expand ranges
            if m.get('start_chunk_index') is not None and t.get('start_chunk_index') is not None:
                m['start_chunk_index'] = min(int(m.get('start_chunk_index')), int(t.get('start_chunk_index')))
            elif t.get('start_chunk_index') is not None:
                m['start_chunk_index'] = int(t.get('start_chunk_index'))
            if m.get('end_chunk_index') is not None and t.get('end_chunk_index') is not None:
                m['end_chunk_index'] = max(int(m.get('end_chunk_index')), int(t.get('end_chunk_index')))
            elif t.get('end_chunk_index') is not None:
                m['end_chunk_index'] = int(t.get('end_chunk_index'))
            continue

        merged.append(t)

    # If too many, keep original order (avoid reordering by length).
    if len(merged) > int(max_topics):
        merged = merged[: int(max_topics)]
    return merged




def _topic_confidence_score(title: str, body: str) -> float:
    """Hybrid confidence: heuristic baseline + optional LLM verification."""
    title = str(title or "").strip()
    body = str(body or "").strip()
    base = 0.45
    if 5 <= len(title) <= 150:
        base += 0.15
    if body:
        base += min(0.2, len(body) / 6000.0)
    if not _AUX_SECTION_RX.match(title):
        base += 0.1

    conf = min(0.95, max(0.05, base))
    if llm_available() and body:
        snippet = re.sub(r"\s+", " ", body).strip()[:1200]
        prompt = (
            "Trả JSON {is_academic_topic: boolean, confidence: number}. "
            "Đánh giá title có phải topic học thuật của sách hay không (0..1)."
        )
        try:
            obj = chat_json(
                messages=[
                    {"role": "system", "content": "Bạn là bộ kiểm định chất lượng topic sách giáo khoa."},
                    {"role": "user", "content": f"{prompt}\nTitle: {title}\nContext: {snippet}"},
                ],
                temperature=0.0,
                max_tokens=120,
            )
            if isinstance(obj, dict):
                llm_conf = float(obj.get("confidence", conf) or conf)
                is_topic = bool(obj.get("is_academic_topic", True))
                llm_conf = min(1.0, max(0.0, llm_conf))
                conf = (0.4 * conf) + (0.6 * llm_conf)
                if not is_topic:
                    conf = min(conf, 0.45)
        except Exception:
            pass

    return float(min(1.0, max(0.0, conf)))


def _merge_duplicate_topics_by_similarity(topics: List[Dict[str, Any]], *, threshold: float = 0.85) -> List[Dict[str, Any]]:
    if not topics:
        return []
    out: list[dict[str, Any]] = []
    for t in topics:
        title = str(t.get("title") or "")
        toks = _title_token_set(title)
        best_i = None
        best = 0.0
        for i, m in enumerate(out):
            score = _jaccard(toks, _title_token_set(str(m.get("title") or "")))
            if score > best:
                best = score
                best_i = i
        if best_i is not None and best >= float(threshold):
            cur = out[best_i]
            conf_cur = float(cur.get("extraction_confidence") or 0.0)
            conf_new = float(t.get("extraction_confidence") or 0.0)
            keep_new = conf_new >= conf_cur
            primary = t if keep_new else cur
            secondary = cur if keep_new else t
            primary_body = str(primary.get("body") or "").strip()
            sec_body = str(secondary.get("body") or "").strip()
            if sec_body and sec_body not in primary_body:
                primary["body"] = (primary_body + "\n\n" + sec_body).strip()
            kws = [str(x).strip().lower() for x in (primary.get("keywords") or []) if str(x).strip()]
            for x in (secondary.get("keywords") or []):
                xx = str(x).strip().lower()
                if xx and xx not in kws:
                    kws.append(xx)
            primary["keywords"] = kws[:16]
            for k in ("start_chunk_index", "end_chunk_index", "page_start", "page_end"):
                if primary.get(k) is None and secondary.get(k) is not None:
                    primary[k] = secondary.get(k)
            out[best_i] = primary
            continue
        out.append(t)
    return out

def _merge_tiny_topics(topics: List[Dict[str, Any]], *, min_body_chars: int) -> List[Dict[str, Any]]:
    """Merge tiny topics so each topic has enough evidence for study material + 3 difficulty levels.

    Deterministic strategy:
    - If a topic body is below min_body_chars, merge it into the NEXT topic (prepend as a subheading).
    - If the LAST topic is tiny, merge it into the PREVIOUS topic.
    - Merge keywords and expand chunk ranges.
    """
    if not topics or int(min_body_chars) <= 0:
        return topics or []

    def _norm_len(s: str) -> int:
        return len(re.sub(r"\s+", " ", str(s or "")).strip())

    # Work on a shallow copy to avoid mutating callers.
    buf: List[Dict[str, Any]] = [dict(t) for t in topics]

    i = 0
    while i < len(buf):
        t = buf[i]
        body = str(t.get('body') or '').strip()
        if _norm_len(body) >= int(min_body_chars):
            i += 1
            continue

        # If it's the only topic, keep it.
        if len(buf) == 1:
            break

        # Prefer merging into the next topic; otherwise merge into previous.
        if i + 1 < len(buf):
            nxt = buf[i + 1]
            sub_title = str(t.get('title') or '').strip()
            sub_body = str(t.get('body') or '').strip()
            prefix = (sub_title + "\n" + sub_body).strip() if sub_title else sub_body
            nxt['body'] = (prefix + "\n\n" + str(nxt.get('body') or '')).strip()

            # keywords
            mk: list[str] = [str(x).strip().lower() for x in (nxt.get('keywords') or []) if str(x).strip()]
            for x in (t.get('keywords') or []):
                xx = str(x).strip().lower()
                if xx and xx not in mk:
                    mk.append(xx)
            nxt['keywords'] = mk[:16]

            # ranges
            if t.get('start_chunk_index') is not None:
                if nxt.get('start_chunk_index') is None:
                    nxt['start_chunk_index'] = int(t.get('start_chunk_index'))
                else:
                    nxt['start_chunk_index'] = min(int(nxt.get('start_chunk_index')), int(t.get('start_chunk_index')))
            if t.get('end_chunk_index') is not None:
                if nxt.get('end_chunk_index') is None:
                    nxt['end_chunk_index'] = int(t.get('end_chunk_index'))
                else:
                    nxt['end_chunk_index'] = max(int(nxt.get('end_chunk_index')), int(t.get('end_chunk_index')))

            # drop current
            buf.pop(i)
            continue

        # last topic: merge into previous
        if i - 1 >= 0:
            prev = buf[i - 1]
            sub_title = str(t.get('title') or '').strip()
            sub_body = str(t.get('body') or '').strip()
            suffix = (sub_title + "\n" + sub_body).strip() if sub_title else sub_body
            prev['body'] = (str(prev.get('body') or '').rstrip() + "\n\n" + suffix).strip()
            pk: list[str] = [str(x).strip().lower() for x in (prev.get('keywords') or []) if str(x).strip()]
            for x in (t.get('keywords') or []):
                xx = str(x).strip().lower()
                if xx and xx not in pk:
                    pk.append(xx)
            prev['keywords'] = pk[:16]
            if t.get('start_chunk_index') is not None:
                if prev.get('start_chunk_index') is None:
                    prev['start_chunk_index'] = int(t.get('start_chunk_index'))
                else:
                    prev['start_chunk_index'] = min(int(prev.get('start_chunk_index')), int(t.get('start_chunk_index')))
            if t.get('end_chunk_index') is not None:
                if prev.get('end_chunk_index') is None:
                    prev['end_chunk_index'] = int(t.get('end_chunk_index'))
                else:
                    prev['end_chunk_index'] = max(int(prev.get('end_chunk_index')), int(t.get('end_chunk_index')))
            buf.pop(i)
            i = max(0, i - 1)
            continue

        i += 1

    return buf


def _mostly_english(text: str) -> bool:
    letters = [ch for ch in (text or "") if ch.isalpha()]
    if len(letters) < 30:
        return False
    non_ascii = sum(1 for ch in letters if ord(ch) > 127)
    return (non_ascii / max(1, len(letters))) < 0.05


def _should_external_enrich(title: str, body: str) -> bool:
    """Decide whether to enrich a topic with external sources.

    This is used ONLY to help "Ít dữ liệu" topics become learnable/quiz-ready,
    and always attaches explicit sources.
    """
    mode = (getattr(settings, 'TOPIC_EXTERNAL_ENRICH', 'off') or 'off').strip().lower()
    if mode == 'off':
        return False
    if mode == 'always':
        return True
    # auto
    txt = re.sub(r"\s+", " ", (body or "")).strip().lower()
    if 'ít dữ liệu' in txt or 'it du lieu' in txt:
        return True
    min_chars = int(getattr(settings, 'TOPIC_EXTERNAL_MIN_BODY_CHARS', 900) or 900)
    # Only enrich when the topic is *clearly* underspecified.
    if len(txt) < max(240, int(min_chars * 0.55)):
        return True
    # Very generic titles + short body are likely underspecified.
    if _is_generic_title(title) and len(txt) < max(420, int(min_chars * 0.8)):
        return True
    return False


def _fallback_teacher_title(body: str) -> str:
    kws = _keywords(body or "", k=8)
    if kws:
        if _mostly_english(body):
            main = kws[0]
            if len(kws) >= 2:
                return f"Overview of {main} and {kws[1]}"[:110]
            return f"Overview of {main}"[:110]
        main = kws[0]
        if len(kws) >= 2:
            return f"Tổng quan về {main} và {kws[1]}"[:110]
        return f"Tổng quan về {main}"[:110]
    return "Nội dung trọng tâm"


def _dedupe_title(title: str, body: str, used: set[str]) -> str:
    key = (title or "").strip().lower()
    if not key or key not in used:
        return title

    # Try to differentiate by appending a keyword that appears in the body
    # but is not already in the title.
    kws = _keywords(body or "", k=10)
    for kw in kws:
        if not kw:
            continue
        if kw.lower() in key:
            continue
        cand = f"{title} — {kw}".strip()
        if cand.lower() not in used and len(cand) >= 6:
            return cand[:255]

    # If keywords don't help, add a short pedagogical suffix.
    for suffix in ("— phần tiếp", "— mở rộng", "— nâng cao", "— bổ sung"):
        cand = f"{title} {suffix}".strip()
        if cand.lower() not in used:
            return cand[:255]

    # Final fallback: numeric disambiguation.
    i = 2
    while True:
        cand = f"{title} ({i})"
        if cand.lower() not in used:
            return cand[:255]
        i += 1



def _de_all_caps_title(title: str) -> str:
    """Convert ALL-CAPS headings into nicer sentence case (best-effort).

    Keeps short acronyms (<=4 letters) as-is.
    """
    s = _clean_line(title)
    if not s:
        return s
    if not _is_all_caps_heading(s):
        return s

    parts = s.split()
    out = []
    for w in parts:
        # keep acronyms like CNN, RNN, AI
        if w.isupper() and len(w) <= 4:
            out.append(w)
        else:
            out.append(w.lower())
    if out:
        # Capitalize the first non-acronym token (or the first token if none)
        for i in range(len(out)):
            if not (out[i].isupper() and len(out[i]) <= 4):
                out[i] = out[i][:1].upper() + out[i][1:]
                break
    return " ".join(out)

def _llm_rewrite_title(body: str, *, old_title: str) -> str | None:
    excerpt = re.sub(r"\s+", " ", (body or "")).strip()[:1600]
    if len(excerpt) < 240:
        return None

    outline = _extract_outline(body, limit=18)
    bullets = _extract_bullets_and_steps(body, limit=10)

    system = (
        "Bạn là GIẢNG VIÊN. Nhiệm vụ: ĐẶT LẠI TIÊU ĐỀ cho một mục/tiểu mục dựa CHỈ trên nội dung được cung cấp. "
        "Không bịa thêm kiến thức mới, không thêm chủ đề ngoài đoạn trích. "
        "Tiêu đề cần giống mục lục sách/giáo viên: ngắn gọn, mô tả đúng ý chính, 6-14 từ. "
        "Tránh các tiền tố chung chung như 'Topic', 'Phần', 'Mục' nếu không cần. "
        "QUAN TRỌNG VỀ ENCODING: Nếu old_title chứa ký tự lạ như: ¸, \\u00AD, ¬, ×, ®, ¦, §, © "
        "hoặc các ký tự Latin-1 không phải tiếng Việt chuẩn thì xem như lỗi font. "
        "Trong trường hợp đó: BỎ QUA hoàn toàn old_title và tạo tiêu đề mới 100% dựa trên body. "
        "Tiêu đề phải là tiếng Việt chuẩn Unicode NFC. "
        "FONT ENCODING NOTICE: Nếu old_title chứa bất kỳ ký tự nào trong {¸ \u00AD ¬ × ® ¦ § © ¹ º » ¼ ½ ¾ ¿} "
        "thì ĐÓ LÀ LỖI FONT TCVN3/VnTime. Trong trường hợp đó: TUYỆT ĐỐI BỎ QUA old_title hoàn toàn. "
        "Tạo tiêu đề mới 100% từ nội dung excerpt và outline_hint cung cấp bên dưới. "
        "Tiêu đề kết quả phải là tiếng Việt Unicode chuẩn NFC, không ký tự lạ. "
        "Chỉ trả JSON hợp lệ: {\"title\": \"...\"}."
    )

    user_parts = [
        f"TIÊU ĐỀ HIỆN TẠI: {old_title}",
        f"NỘI DUNG (trích): {excerpt}",
    ]
    if outline:
        user_parts.append("DẤU HIỆU HEADING/TRONG MỤC (nếu có):\n- " + "\n- ".join(outline[:18]))
    if bullets:
        user_parts.append("GẠCH ĐẦU DÒNG/QUY TRÌNH (nếu có):\n- " + "\n- ".join(bullets[:10]))

    user = "\n\n".join(user_parts)

    try:
        obj = chat_json(
            messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
            temperature=0.15,
            max_tokens=120,
        )
        if not isinstance(obj, dict):
            return None
        cand = str(obj.get('title') or '').strip()
        cand = _normalize_title_candidate(cand)
        if not cand:
            return None
        # Still generic? reject.
        if _is_generic_title(cand):
            return None
        return cand
    except Exception:
        return None


def _clean_line(line: str) -> str:
    s = (line or "").replace(" ", " ").strip()
    s = re.sub(r"^[\-•\*]+\s+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return s

    # Repair common PDF/OCR spacing artifacts early so heading detection sees clean text.
    # (e.g., "Tínhtoá n" -> "Tính toán", "Pytho n" -> "Python")
    try:
        s2 = repair_ocr_spacing_line(s)
        if s2:
            s = re.sub(r"\s+", " ", s2).strip()
    except Exception:
        pass

    # Nếu line có vẻ lỗi font, thử fix trước khi dùng làm heading
    try:
        from app.services.vietnamese_font_fix import detect_broken_vn_font, fix_vietnamese_font_encoding, fix_vietnamese_encoding

        if detect_broken_vn_font(s):
            fixed = fix_vietnamese_font_encoding(s)
            if fixed and not detect_broken_vn_font(fixed):
                s = fixed
    except Exception:
        pass

    # Repair spaced-letter headings like "C h ư ơ n g" or "t i n h to a n".
    tokens = s.split()
    if len(tokens) >= 5:
        single_alpha = sum(1 for t in tokens if len(t) == 1 and t.isalpha())
        looks_mathy = bool(re.search(r"[0-9=+\-*/^]", s))
        if single_alpha >= 3 and not (looks_mathy and single_alpha < 6):
            math_vars = set('xyzuvwtnmk')
            out: list[str] = []
            i = 0
            while i < len(tokens):
                t = tokens[i]
                if t.isalpha() and len(t) <= 2:
                    j = i
                    group: list[str] = []
                    one_cnt = 0
                    while j < len(tokens):
                        tj = tokens[j]
                        if tj.isalpha() and len(tj) <= 2:
                            group.append(tj)
                            if len(tj) == 1:
                                one_cnt += 1
                            j += 1
                        else:
                            break
                    total_chars = sum(len(x) for x in group)
                    if (one_cnt >= 2 and total_chars >= 5) or (one_cnt >= 3) or (len(group) >= 5 and one_cnt >= 1):
                        if all((len(x) == 1 and x.lower() in math_vars) for x in group):
                            out.extend(group)
                        else:
                            out.append(''.join(group))
                        i = j
                        continue
                out.append(t)
                i += 1
            s = ' '.join(out)

    # Stronger OCR/PDF repair (handles short split patterns like "Lập t rình").
    # Safe for code/math lines (they are detected and left unchanged).
    try:
        s2 = repair_ocr_spacing_line(s)
        if s2:
            s = re.sub(r"\s+", " ", s2).strip()
    except Exception:
        pass

    return s


# ===== TOC + lesson-mode splitting helpers =====
_TOC_START_RX = re.compile(
    r"^\s*(?:mục\s*lục|muc\s*luc|table\s+of\s+contents|contents)\s*$",
    re.IGNORECASE,
)
# IMPORTANT: Many Vietnamese PDFs do NOT use a long '=' bar to end TOC.
# We accept common divider lines too, and also add a hard cap in code (TOC_MAX_LINES).
_TOC_END_RX = re.compile(r"^\s*(?:={8,}|-{8,}|_{8,}|—{6,}|–{6,})\s*$")

# Lesson headings: Bài 1., BÀI 12, bai 3 ... (allow NBSP)
_LESSON_HEADING_RX = re.compile(
    r"^\s*(?:[\-•\*]+\s*)?(?:bài|bai)[\s\u00A0]+\d{1,3}\b",
    re.IGNORECASE,
)

# TOC chapter lines commonly look like:
#   "Chương 2: Tính toán Python .......... 15"
#   "Chương 3 Các kiểu dữ liệu ..... 21"
_TOC_CHAPTER_LINE_RX = re.compile(
    r"^\s*(?:chương|chuong|chapter)\s+(\d{1,3}|[IVXLCDM]{1,6})\b\s*[:\-–—\.]?\s*(.*?)\s*(?:\.{2,}\s*\d{1,4}|\s+\d{1,4})\s*$",
    flags=re.IGNORECASE,
)
_TOC_TOPLEVEL_RX = re.compile(
    r"^\s*(mở\s*đầu|mo\s*dau|giới\s*thiệu|gioi\s*thieu|lời\s*nói\s*đầu|loi\s*noi\s*dau)\b\s*(?:\.{2,}\s*\d{1,4}|\s+\d{1,4})\s*$",
    flags=re.IGNORECASE,
)


def _roman_to_int(s: str) -> int | None:
    if not s:
        return None
    s = s.upper().strip()
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    if any(ch not in vals for ch in s):
        return None
    total = 0
    prev = 0
    for ch in reversed(s):
        v = vals[ch]
        if v < prev:
            total -= v
        else:
            total += v
            prev = v
    return total if total > 0 else None


def _parse_toc_title_map(raw_lines: list[str], cleaned_lines: list[str]) -> dict[int, str]:
    """Parse chapter titles from TOC to get clean names even when body headings are OCR-noisy."""
    out: dict[int, str] = {}
    in_toc = False
    toc_lines = 0
    TOC_MAX_LINES = 260
    for i, cl in enumerate(cleaned_lines):
        if not cl:
            continue
        if _TOC_START_RX.match(cl):
            in_toc = True
            toc_lines = 0
            continue
        if in_toc:
            toc_lines += 1
            if _TOC_END_RX.match(cl) or toc_lines >= TOC_MAX_LINES:
                in_toc = False
                continue

            m = _TOC_CHAPTER_LINE_RX.match(cl)
            if m:
                idx_raw = (m.group(1) or "").strip()
                title_raw = (m.group(2) or "").strip()
                n: int | None = None
                if idx_raw.isdigit():
                    n = int(idx_raw)
                else:
                    n = _roman_to_int(idx_raw)
                if n is not None:
                    title = _clean_line(title_raw)
                    title = re.sub(r"\s+", " ", title).strip()
                    if title:
                        out[n] = title[:180]
                continue

            # Also detect an explicit "Mở đầu" in TOC (optional)
            if _TOC_TOPLEVEL_RX.match(cl):
                out[0] = "Mở đầu"

    return out


def _normalize_vn_pairs(text: str) -> str:
    """Conservative unglue pass for very common Vietnamese collocations.

    This helps cases like 'máytínhthựchiện' (missing spaces) and still keeps
    code/math lines mostly intact.
    """
    if not text:
        return ""
    # Apply on each line to avoid damaging code blocks.
    lines = (text or "").replace("\r", "").split("\n")
    out_lines: list[str] = []
    pairs = [
        ("lập", "trình"),
        ("máy", "tính"),
        ("điều", "khiển"),
        ("thực", "hiện"),
        ("nhiệm", "vụ"),
        ("ngôn", "ngữ"),
        ("dữ", "liệu"),
        ("thư", "viện"),
        ("phiên", "bản"),
        ("cú", "pháp"),
        ("phương", "trình"),
        ("môi", "trường"),
        ("tính", "toán"),
        ("cài", "đặt"),
        ("trực", "quan"),
    ]
    for ln in lines:
        s = ln
        # Only run when line contains Vietnamese letters; avoids touching code.
        if any(ord(ch) > 127 for ch in s if ch.isalpha()):
            for a, b in pairs:
                s = re.sub(rf"\b{a}\s*{b}\b", f"{a} {b}", s, flags=re.IGNORECASE)
        out_lines.append(s)
    return "\n".join(out_lines)


def _is_lesson_heading_line(line: str) -> bool:
    s = _clean_line(line)
    return bool(s and _LESSON_HEADING_RX.match(s))


def _detect_lesson_mode(full_text: str) -> bool:
    """Return True if we should split topics primarily by lessons (Bài N).

    Modes:
    - off: always use heading-based splitter
    - always: always use lesson splitter
    - auto: enable when we detect >=4 lesson headings outside TOC
    """
    mode = (getattr(settings, 'TOPIC_LESSON_MODE', 'auto') or 'auto').strip().lower()
    if mode == 'off':
        return False
    if mode == 'always':
        # Prefer lesson-mode splitting, but only when the document actually contains lesson headings.
        # This prevents a hard fallback to LLM segmentation for documents that don't use the "Bai N" format.
        raw_lines = (full_text or '').replace('\r', '').split('\n')
        in_toc = False
        toc_lines = 0
        TOC_MAX_LINES = 260
        for ln in raw_lines:
            cl = _clean_line(ln)
            if not cl:
                continue
            if _TOC_START_RX.match(cl):
                in_toc = True
                toc_lines = 0
                continue
            if in_toc:
                toc_lines += 1
                if _TOC_END_RX.match(cl) or toc_lines >= TOC_MAX_LINES:
                    in_toc = False
                continue
            if _is_lesson_heading_line(cl) and not _is_bad_heading_candidate(cl):
                return True
        return False

    raw_lines = (full_text or '').replace('\r', '').split('\n')
    in_toc = False
    toc_lines = 0
    TOC_MAX_LINES = 260
    cnt = 0
    for ln in raw_lines:
        cl = _clean_line(ln)
        if not cl:
            continue
        if _TOC_START_RX.match(cl):
            in_toc = True
            toc_lines = 0
            continue
        if in_toc:
            toc_lines += 1
            if _TOC_END_RX.match(cl) or toc_lines >= TOC_MAX_LINES:
                in_toc = False
            continue
        if _is_lesson_heading_line(cl) and not _is_bad_heading_candidate(cl):
            cnt += 1
            if cnt >= 4:
                return True
    return False


def _detect_toc_end_offset(text: str) -> int:
    """Best-effort char offset just AFTER the TOC section.

    Used to avoid matching headings inside TOC when mapping topics to chunks.
    Returns 0 if TOC not found.
    """
    try:
        raw = (text or "").replace("\r", "").replace("\u00A0", " ")
        if not raw:
            return 0
        lines = raw.split("\n")
        in_toc = False
        pos = 0
        for ln in lines:
            cl = _clean_line(ln)
            ln_len = len(ln) + 1  # newline
            if not in_toc and _TOC_START_RX.match(cl):
                in_toc = True
                pos += ln_len
                continue
            if in_toc and _TOC_END_RX.match(cl):
                pos += ln_len
                return max(0, pos)
            pos += ln_len
        return 0
    except Exception:
        return 0


def _map_topics_to_chunk_ranges_by_anchors(
    topics_raw: List[Dict[str, Any]],
    chunks_texts: List[str],
    *,
    toc_end_hint: int = 0,
) -> List[Tuple[Optional[int], Optional[int]]]:
    """Map full-text extracted topics to (start_chunk_index,end_chunk_index) via heading anchors.

    We split topics on full_text (stable), then locate each topic's heading line in the concatenated
    chunk texts to obtain tight chunk ranges.
    """
    if not topics_raw or not chunks_texts:
        return []

    parts: List[str] = []
    offsets: List[int] = [0]
    total = 0
    for tx in chunks_texts:
        s = (tx or "").replace("\r", "")
        parts.append(s)
        total += len(s)
        offsets.append(total)
    big = "".join(parts)
    big_norm = big.replace("\u00A0", " ")

    toc_end = int(toc_end_hint or 0)
    if toc_end <= 0:
        toc_end = _detect_toc_end_offset(big_norm)

    # Some chunkers remove the '=' separator lines, making TOC end hard to detect.
    # Fallback: find the first REAL lesson heading (often written as "BÀI ..." in uppercase) and
    # use it as a safe starting point.
    start_hint = max(0, toc_end)
    if start_hint <= 0:
        m = re.search(r"\n\s*BÀI\s+\d{1,3}\.", big_norm)
        if m:
            start_hint = max(0, int(m.start()))

    def _offset_to_chunk(off: int) -> int:
        lo, hi = 0, len(offsets) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if offsets[mid + 1] <= off:
                lo = mid + 1
            else:
                hi = mid
        return max(0, min(len(chunks_texts) - 1, lo))

    anchor_offsets: List[Optional[int]] = []
    low_big = big_norm.lower()
    for t in topics_raw:
        anchor = _clean_line(str(t.get('title') or ''))
        if not anchor:
            anchor_offsets.append(None)
            continue
        # 1) Prefer exact case-sensitive match after the start hint.
        idx = big_norm.find(anchor, start_hint)
        if idx < 0:
            idx = big_norm.find(anchor)
        # 2) Fallback: case-insensitive match.
        if idx < 0:
            low_anchor = anchor.lower()
            idx = low_big.find(low_anchor, start_hint)
            if idx < 0:
                idx = low_big.find(low_anchor)
        anchor_offsets.append(idx if idx >= 0 else None)

    ranges: List[Tuple[Optional[int], Optional[int]]] = []
    for i, start_off in enumerate(anchor_offsets):
        if start_off is None:
            ranges.append((None, None))
            continue
        end_off = None
        for j in range(i + 1, len(anchor_offsets)):
            if anchor_offsets[j] is not None:
                end_off = anchor_offsets[j]
                break
        s_idx = _offset_to_chunk(int(start_off))
        e_idx = _offset_to_chunk(int(end_off - 1)) if end_off is not None else (len(chunks_texts) - 1)
        if e_idx < s_idx:
            e_idx = s_idx
        ranges.append((s_idx, e_idx))

    return ranges


def _topic_llm_filter_enabled() -> bool:
    mode = (getattr(settings, 'TOPIC_LLM_FILTER', 'auto') or 'auto').strip().lower()
    if mode == 'off':
        return False
    if mode == 'always':
        return True
    return bool(llm_available())


def _llm_filter_topics(norm_raw: List[Dict[str, Any]], *, max_keep: int) -> List[Dict[str, Any]]:
    """LLM post-pass: drop/merge/rename topics to look like a teacher-curated outline."""
    if not norm_raw or not llm_available():
        return norm_raw

    items = []
    for i, t in enumerate(norm_raw[: max(10, int(max_keep) * 3)]):
        body = str(t.get('body') or '')
        preview = re.sub(r"\s+", " ", body).strip()[:260]
        items.append({'idx': i, 'title': str(t.get('title') or '')[:255], 'preview': preview, 'len': len(body)})

    system = (
        "Bạn là giáo viên. Hãy LỌC danh sách topic học tập cho học sinh. "
        "Loại bỏ các mục như: mục lục, lời nói đầu, phụ lục thuần công thức, đáp án, bài tập tách riêng. "
        "Chỉ được chọn/đổi tên/gộp từ danh sách đã cho, không tạo topic mới. "
        "Giữ đúng thứ tự xuất hiện (không reorder). "
        "Trả JSON: {topics:[{idx,new_title?,merge_to_prev?}]}."
    )
    user = f"TOPIC ỨNG VIÊN (JSON): {json.dumps(items, ensure_ascii=False)}\nmax_keep={int(max_keep)}"
    try:
        obj = chat_json(
            messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
            temperature=0.1,
            max_tokens=900,
        )
    except Exception:
        return norm_raw

    chosen = obj.get('topics') if isinstance(obj, dict) else None
    if not isinstance(chosen, list) or not chosen:
        return norm_raw

    out: List[Dict[str, Any]] = []
    for it in chosen:
        if not isinstance(it, dict):
            continue
        try:
            idx = int(it.get('idx'))
        except Exception:
            continue
        if idx < 0 or idx >= len(norm_raw):
            continue
        merge_prev = bool(it.get('merge_to_prev'))
        new_title = str(it.get('new_title') or '').strip()
        cur = dict(norm_raw[idx])
        if new_title:
            cur['title'] = new_title[:255]
        if merge_prev and out:
            prev = out[-1]
            prev['body'] = (str(prev.get('body') or '') + "\n\n" + str(cur.get('body') or '')).strip()
            kws: list[str] = []
            for x in (prev.get('keywords') or []) + (cur.get('keywords') or []):
                s = str(x).strip().lower()
                if s and s not in kws:
                    kws.append(s)
            prev['keywords'] = kws[:16]
        else:
            out.append(cur)
        if len(out) >= int(max_keep):
            break

    return out or norm_raw


def _is_all_caps_heading(line: str) -> bool:
    s = _clean_line(line)
    if not s:
        return False
    # Never treat MCQ answer choices / question items as headings.
    # Example: "A. 1/2 B. 1/4 C. 1/6 D. 1/8".
    if _is_mcq_choices_line(s) or _looks_like_question_item(s):
        return False
    if len(s) < 6 or len(s) > 120:
        return False
    letters = [ch for ch in s if ch.isalpha()]
    if len(letters) < 4:
        return False
    upper = sum(1 for ch in letters if ch.isupper())
    # 80%+ uppercase letters is a strong signal for a heading in PDFs
    return (upper / max(1, len(letters))) >= 0.8


def _looks_like_question_item(line: str) -> bool:
    """Heuristic: detect exercise/question list items so we don't treat them as topic headings."""
    s = _clean_line(line).strip()
    if not s:
        return False

    sl = s.lower()

    # Common question-number patterns (often appear alone on a line)
    # e.g. "Q11.", "Câu 12:", "Cau 5)"
    if re.match(r"^(?:q|câu|cau)\s*\d{1,3}\b", sl):
        return True

    # Obvious question marks
    if "?" in s:
        return True

    # Multiple-choice patterns on one line
    if re.search(r"\bA\.\s+.+\bB\.\s+.+", s):
        return True

    # Numbered item with ')' (common for exercises: 1) 2) ...)
    m = re.match(r"^\s*(?:[\-•\*]+\s*)?(\d{1,2}(?:\.\d{1,3}){0,4})\s*([\)\.:])\s+(.*)$", s)
    if m:
        punct = m.group(2)
        rest = (m.group(3) or "").strip()
        if punct == ")":
            return True

        # Imperative/question verbs (VN/EN) often indicate an exercise line, not a section title
        first_word = (re.findall(r"[A-Za-zÀ-ỹà-ỹ]+", rest)[:1] or [""])[0].lower()
        vn_verbs = {
            "tính","giải","giải_thích","giải-thích","chứng","chứng_minh","chứng-minh","hãy","nêu","viết",
            "cho","dựa","nếu","tìm","so","sánh","trình","bày","phân","tích","nhận","xét","lấy",
        }
        en_verbs = {"calculate","compute","find","explain","prove","show","write","derive","determine","describe","analyze"}
        if first_word in vn_verbs or first_word in en_verbs:
            return True

        # Very long numbered lines are usually exercises/instructions
        if len(rest) >= 70:
            return True

    return False


def _is_bad_heading_candidate(line: str) -> bool:
    """Reject lines that commonly appear as table rows / definitions / artifacts."""
    s = _clean_line(line)
    if not s:
        return True

    def _has_encoding_noise(s: str, threshold: float = 0.20) -> bool:
        """True nếu > threshold ký tự lạ (dấu hiệu lỗi font VN cũ)."""
        if not s or len(s) < 4:
            return False
        valid = sum(
            1
            for ch in s
            if (
                0x20 <= ord(ch) <= 0x7E
                or 0x00C0 <= ord(ch) <= 0x024F
                or 0x1E00 <= ord(ch) <= 0x1EFF
                or ch in " \t\n\r"
            )
        )
        return (valid / len(s)) < (1.0 - threshold)

    if _has_encoding_noise(s):
        return True  # Heading lỗi encoding → bỏ qua

    sl = s.lower()

    # Never promote question blocks / MCQ answer choices into standalone topics.
    if _looks_like_question_item(s) or _is_mcq_choices_line(s):
        return True

    # Never promote practice/answer-key sections into standalone topics.
    # These should be kept inside the nearest related learning topic.
    if _AUX_SECTION_RX.match(s):
        return True

    # UI/meta markers
    if sl in {"quiz-ready", "ý chính", "y chinh", "khái niệm", "khai niem", "ít dữ liệu", "it du lieu"}:
        return True

    # Table row artifacts: "2 | Bình | 101 | B1" or similar
    if "|" in s:
        if re.match(r"^\s*\d+\s*\|\s*\S+", s):
            return True
        if s.count("|") >= 2:
            return True

    # URLs / hashes / file paths should not be headings
    if "http://" in sl or "https://" in sl or "www." in sl:
        return True

    # Equations belong in body, never as heading
    if any(op in s for op in ["=", "→", "->", "⇒"]):
        return True

    # Definition lines with ':' are usually NOT headings unless they explicitly start with a label.
    if ":" in s or "：" in s:
        if not (_LABEL_PREFIX_RX.match(s) or _APPENDIX_PREFIX_RX.match(s)):
            return True

    # Too short or too long
    if len(s) < 6 or len(s) > 140:
        return True

    return False


def validate_and_repair_topics(topics: list[dict]) -> list[dict]:
    """
    Post-process: kiểm tra title/body lỗi font, tự repair hoặc drop.
    Gọi trong extract_topics() ngay trước dòng return cuối.
    """
    try:
        from app.services.vietnamese_font_fix import detect_broken_vn_font
    except ImportError:
        return topics  # Graceful fallback

    out = []
    for t in topics:
        title = str(t.get('title') or '')
        body = str(t.get('body') or '')
        title_bad = len(title) > 4 and detect_broken_vn_font(title)
        body_bad = len(body) > 60 and detect_broken_vn_font(body)

        if title_bad and body_bad:
            continue  # Cả 2 đều lỗi → drop topic này

        if title_bad and not body_bad:
            # Rewrite title từ body content
            new_title = _llm_rewrite_title(body, old_title=title)
            if new_title:
                t = {**t, 'title': new_title, '_title_was_repaired': True}

        out.append(t)
    return out


def validate_topic_quality(topics: list[dict]) -> list[dict]:
    """
    Post-process: kiểm tra và lọc topic có tiêu đề/body lỗi font.
    Nếu title lỗi nhưng body OK → dùng LLM rewrite title từ body.
    Nếu cả title lẫn body đều lỗi → drop topic đó.
    """
    return validate_and_repair_topics(topics)


def _maybe_title_from_quiz_ready(cleaned_lines: List[str], i: int) -> tuple[int, str] | None:
    """Heuristic: if line i is 'Quiz-ready', the previous non-empty line is *often* the section title.

    Important: many teacher/AI docs place "Bài tập..." / "Đáp án..." right before "Quiz-ready".
    Those MUST NOT become standalone topics, so we skip auxiliary headings.
    """
    if i <= 0:
        return None

    # Only search back a small window to avoid accidentally jumping to a much older title
    # and creating duplicate topic boundaries.
    max_back_non_empty = 6
    seen_non_empty = 0
    j = i - 1
    while j >= 0 and seen_non_empty < max_back_non_empty:
        prev = cleaned_lines[j]
        if not prev or not prev.strip():
            j -= 1
            continue
        seen_non_empty += 1
        title = _clean_line(prev)
        if not title:
            j -= 1
            continue
        if _looks_like_question_item(title):
            j -= 1
            continue
        # Skip practice/answer-key headings and other bad candidates.
        if _is_bad_heading_candidate(title):
            j -= 1
            continue
        return (j, title[:255])
    return None


def _is_heading(line: str) -> bool:
    """Broad heading detection (used for outline extraction)."""
    s = _clean_line(line)
    if not s:
        return False

    if _HEADING_HINT.search(s):
        return True
    if _NUM_HEADING.match(s) and not _looks_like_question_item(s):
        return True
    if _ROMAN_HEADING.match(s):
        return True
    if _is_all_caps_heading(s):
        return True

    return False


def _is_topic_heading(line: str) -> bool:
    """Stricter heading detection for TOPIC boundaries.

    We intentionally ignore exercise list items like "1) Tính ..." or "2) Giải thích ...",
    otherwise the system will split one topic into many tiny topics.
    """
    s = _clean_line(line)
    if not s:
        return False

    # Never split topics on question blocks / MCQ choices.
    if _looks_like_question_item(s) or _is_mcq_choices_line(s):
        return False

    sl = s.lower().strip()
    # Appendix headings often come as:
    #   "PHỤ LỤC 3) ...", "PHỤ LỤC 1. ..."
    # The generic regex may miss these (no ':' / '—'), so we treat them as hard boundaries.
    if re.match(r'^(phụ\s*lục|phu\s*luc|appendix)\s+(\d{1,3}|[ivxlcdm]{1,6})\b', sl, flags=re.IGNORECASE):
        return True
    # NOTE: We intentionally do NOT treat "Bài tập"/"Đáp án"/"Mini-quiz" as TOPIC boundaries.
    # Those are auxiliary sections and should live inside the closest related topic.

    # Strong signals: explicit section labels like "Chủ đề:" / "Chương 1" / "Mục 2.3"
    if _HEADING_HINT.search(s):
        return True

    # All-caps headings often represent big section breaks
    if _is_all_caps_heading(s):
        return True

    # Numeric headings only when they look like section titles (not questions)
    m = _NUM_HEADING.match(s)
    if m and not _looks_like_question_item(s):
        # Depth cap: avoid over-splitting on deep headings like 2.3.1, 3.2.4 ...
        num = str(m.group(2) or '')
        depth = num.count('.') + 1 if num else 1
        try:
            max_depth = int(getattr(settings, 'TOPIC_NUM_HEADING_MAX_DEPTH', 2) or 2)
        except Exception:
            max_depth = 2
        if depth > max_depth:
            return False

        # Keep short titles only (avoid splitting inside long paragraphs)
        tok = _WORD_RX.findall(s)
        if len(tok) <= 12 and len(s) <= 80:
            return True

    # Roman headings (I. II. ...) - rare, but keep for structured docs
    if _ROMAN_HEADING.match(s) and len(s) <= 90 and not _looks_like_question_item(s):
        return True

    return False


def _sentences(text: str) -> List[str]:
    t = (text or "").strip()
    if not t:
        return []
    # keep it simple; Vietnamese texts often use '.' well enough.
    parts = re.split(r"(?<=[\.!\?])\s+", t)
    out = [p.strip() for p in parts if p and p.strip()]
    return out


def _keywords(text: str, k: int = 8) -> List[str]:
    toks = [t.lower() for t in _WORD_RX.findall(text or "")]
    freq: Dict[str, int] = {}
    for w in toks:
        if len(w) < 3:
            continue
        if w in _STOP:
            continue
        # drop pure numbers
        if w.isdigit():
            continue
        freq[w] = freq.get(w, 0) + 1
    items = sorted(freq.items(), key=lambda x: (x[1], len(x[0])), reverse=True)
    out: List[str] = []
    for w, _ in items:
        if w in out:
            continue
        out.append(w)
        if len(out) >= k:
            break
    return out


def _extract_by_lessons(full_text: str) -> List[Dict[str, Any]]:
    """Split topics only by 'Bài N...' headings (textbook lesson-mode).

    This avoids over-splitting by subheadings like '1. Mục tiêu', '2. Khái niệm' etc.
    Also skips Table-of-Contents regions.
    """
    raw = [ln for ln in (full_text or '').replace('\r', '').split('\n')]
    lines = [_clean_line(ln) for ln in raw]
    if not any(ln.strip() for ln in lines):
        return []

    idxs: List[int] = []
    in_toc = False
    for i, ln in enumerate(lines):
        cl = _clean_line(ln)
        if not cl:
            continue

        # Skip headings inside Table of Contents
        if _TOC_START_RX.match(cl):
            in_toc = True
            continue
        if in_toc and _TOC_END_RX.match(cl):
            in_toc = False
            continue
        if in_toc:
            continue
        if _TOC_START_RX.match(cl):
            in_toc = True
            continue
        if in_toc and _TOC_END_RX.match(cl):
            in_toc = False
            continue
        if in_toc:
            continue
        if _is_lesson_heading_line(cl) and not _is_bad_heading_candidate(cl):
            idxs.append(int(i))

    if not idxs:
        # Fallback: infer "chapters" from numbered subsections like 1.1, 2.3 ...
        num_rx = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\b")
        firsts = []
        seen = set()
        for i, ln in enumerate(lines):
            m = num_rx.match(ln or '')
            if not m:
                continue
            n = int(m.group(1))
            if n in seen:
                continue
            seen.add(n)
            firsts.append((i, n, ln))
        if not firsts:
            return []
        idxs = [i for i, _, _ in firsts]
        # Build pseudo chapter titles: "Chương N - <first subsection heading>"
        pseudo_titles = {i: f"Chương {n} - {(_clean_line(ln) or '').strip()}"[:255] for i, n, ln in firsts}
        # Store for later use when creating topics
        _pseudo_title_map = pseudo_titles
    else:
        _pseudo_title_map = {}

    topics: List[Dict[str, Any]] = []
    for j, i in enumerate(idxs):
        title = _clean_line(lines[i])
        start = i + 1
        end = (idxs[j + 1] if j + 1 < len(idxs) else len(lines))
        body = '\n'.join(raw[start:end]).strip()
        if len(re.sub(r'\s+', ' ', body)) < 35:
            continue
        topics.append({'title': title[:255], 'body': body})
    return topics


def _extract_by_lessons_in_chunks(chunks_texts: List[str]) -> List[Dict[str, Any]]:
    """Chunk-aware lesson-mode splitter (stable chunk ranges).

    Skips TOC across chunk boundaries and only uses 'Bài N' headings as topic starts.
    """
    if not chunks_texts:
        return []

    starts: List[Tuple[int, int, str]] = []
    seen: set[Tuple[int, int]] = set()
    in_toc = False

    for ci, tx in enumerate(chunks_texts):
        if not tx:
            continue
        raw_lines = tx.replace('\r', '').split('\n')
        cleaned = [_clean_line(ln) for ln in raw_lines]

        for li, cl in enumerate(cleaned):
            if not cl:
                continue
            if _TOC_START_RX.match(cl):
                in_toc = True
                continue
            if in_toc and _TOC_END_RX.match(cl):
                in_toc = False
                continue
            if in_toc:
                continue
            if _is_lesson_heading_line(cl) and not _is_bad_heading_candidate(cl) and (ci, li) not in seen:
                seen.add((ci, li))
                starts.append((int(ci), int(li), cl[:255]))

    starts.sort(key=lambda x: (x[0], x[1]))
    if not starts:
        return []

    topics: List[Dict[str, Any]] = []
    for j, (start_ci, start_li, title) in enumerate(starts):
        if j + 1 < len(starts):
            next_ci, next_li, _ = starts[j + 1]
            end_ci = int(next_ci)
            end_li = int(next_li) - 1
        else:
            end_ci = int(len(chunks_texts) - 1)
            end_li = None

        if end_ci < start_ci:
            continue

        body_parts: List[str] = []
        for ci in range(int(start_ci), int(end_ci) + 1):
            tx = chunks_texts[ci] or ''
            raw_lines = tx.replace('\r', '').split('\n')

            from_i = int(start_li) + 1 if ci == int(start_ci) else 0
            if ci == int(end_ci) and end_li is not None:
                to_i = max(from_i, int(end_li) + 1)
            else:
                to_i = len(raw_lines)

            seg = '\n'.join(raw_lines[from_i:to_i]).strip()
            if seg:
                body_parts.append(seg)

        body = '\n\n'.join(body_parts).strip()
        if len(re.sub(r'\s+', ' ', body)) < 35:
            continue

        topics.append({
            'title': title,
            'body': body,
            'start_chunk_index': int(start_ci),
            'end_chunk_index': int(end_ci),
        })

    return topics


def _extract_by_headings(full_text: str) -> List[Dict[str, Any]]:
    raw = [ln for ln in (full_text or "").replace("\r", "").split("\n")]
    lines = [_clean_line(ln) for ln in raw]
    # keep empty lines (needed for look-back), but we'll index non-empty headings only
    if not any(ln.strip() for ln in lines):
        return []

    # Find heading line indexes.
    # Besides explicit labels (Chủ đề/Phụ lục/Chương...), we also treat the line BEFORE "Quiz-ready"
    # as a heading. This fixes docs where section titles are just "Toán học (...)".
    idxs: set[int] = set()
    in_toc = False
    for i, ln in enumerate(lines):
        cl = _clean_line(ln)
        if not cl:
            continue

        # Skip headings inside Table of Contents
        if _TOC_START_RX.match(cl):
            in_toc = True
            continue
        if in_toc and _TOC_END_RX.match(cl):
            in_toc = False
            continue
        if in_toc:
            continue

        if cl.strip().lower() == 'quiz-ready':
            maybe = _maybe_title_from_quiz_ready(lines, i)
            if maybe:
                j, _title = maybe
                idxs.add(int(j))
            continue
        if _is_topic_heading(cl) and not _is_bad_heading_candidate(cl):
            idxs.add(int(i))
            continue

        # 3) Soft subject headings (common in teacher notes): title-like line followed by markers.
        if _is_soft_topic_heading(cl, lines, i):
            idxs.add(int(i))

    idxs = sorted(list(idxs))

    if not idxs:
        # Fallback: infer "chapters" from numbered subsections like 1.1, 2.3 ...
        num_rx = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\b")
        firsts = []
        seen = set()
        for i, ln in enumerate(lines):
            m = num_rx.match(ln or '')
            if not m:
                continue
            n = int(m.group(1))
            if n in seen:
                continue
            seen.add(n)
            firsts.append((i, n, ln))
        if not firsts:
            return []
        idxs = [i for i, _, _ in firsts]
        # Build pseudo chapter titles: "Chương N - <first subsection heading>"
        pseudo_titles = {i: f"Chương {n} - {(_clean_line(ln) or '').strip()}"[:255] for i, n, ln in firsts}
        # Store for later use when creating topics
        _pseudo_title_map = pseudo_titles
    else:
        _pseudo_title_map = {}

    # Avoid TOC-like false positives: too many headings in short text
    if len(idxs) >= 14 and len(lines) < 250:
        return []

    topics: List[Dict[str, Any]] = []
    for j, i in enumerate(idxs):
        title = _clean_line(lines[i])
        start = i + 1
        end = (idxs[j + 1] if j + 1 < len(idxs) else len(lines))
        body_lines = [x for x in raw[start:end]]
        body = "\n".join(body_lines).strip()
        topics.append({"title": title, "body": body})

    # Filter extremely tiny topics (usually extraction artefacts), but DO NOT merge by default.
    out: List[Dict[str, Any]] = []
    for t in topics:
        title = str(t.get("title") or "").strip()
        body = str(t.get("body") or "").strip()
        if len(title) < 4:
            continue
        # Allow smaller sections in "ít dữ liệu" docs; quiz readiness is handled separately.
        if len(body) < 25:
            continue
        out.append({"title": title[:255], "body": body})

    return out


def _fallback_segment(full_text: str, k: int = 6) -> List[Dict[str, Any]]:
    t = (full_text or "").strip()
    if not t:
        return []

    # Prefer paragraph-based segmentation
    paras = [p.strip() for p in re.split(r"\n{2,}", t) if p and p.strip()]
    if not paras:
        paras = [t]

    # Determine k by text length (3..8)
    k = int(k)
    if k <= 0:
        k = 6
    k = max(3, min(8, k))

    total_len = sum(len(p) for p in paras)
    target = max(600, total_len // k)

    segs: List[str] = []
    buf: List[str] = []
    cur = 0
    for p in paras:
        buf.append(p)
        cur += len(p)
        if cur >= target and len(segs) < k - 1:
            segs.append("\n\n".join(buf).strip())
            buf = []
            cur = 0
    if buf:
        segs.append("\n\n".join(buf).strip())

    topics: List[Dict[str, Any]] = []
    for i, seg in enumerate(segs):
        # Deterministic fallback, but DO NOT include chapter/section numbering.
        title = _fallback_teacher_title(seg)
        topics.append({"title": title[:255], "body": seg})

    return topics




def _first_heading_in_chunk(text: str) -> tuple[str, int] | None:
    """Return (heading_line, line_index) if a heading is detected near the top of a chunk."""
    if not text:
        return None
    raw_lines = [ln for ln in (text or '').replace('\r', '').split('\n')]
    cleaned = [_clean_line(ln) for ln in raw_lines]
    # consider only first few non-empty lines
    cand: list[tuple[int, str]] = []
    for i, ln in enumerate(cleaned[:10]):
        if not ln:
            continue
        cand.append((i, ln))
        if len(cand) >= 4:
            break
    for i, ln in cand:
        if _is_topic_heading(ln):
            return (ln[:255], i)
    return None


def _headings_in_chunk(text: str, *, max_lines: int = 500) -> list[tuple[int, str]]:
    """Return all topic headings detected inside a chunk.

    Fix for the "càng sửa càng kém" issue:
    - Many synthetic/docs can pack MULTIPLE topics into a single chunk.
    - The previous version only scanned the first ~60 non-empty lines, so later headings were missed,
      causing topics to "dính" (Math swallowing Study Skills, etc.).

    New approach:
    - Scan the whole chunk (bounded by max_lines for pathological cases).
    - Use "Quiz-ready" as a strong boundary signal: the line BEFORE it is usually the topic title.
    - Keep explicit headings like "Chủ đề: ..." anywhere in the chunk.
    """
    if not text:
        return []

    raw_lines = [ln for ln in (text or '').replace('\r', '').split('\n')]
    cleaned = [_clean_line(ln) for ln in raw_lines]

    skip = {
        'topic outline (học & ra đề)'.lower(),
        'topic outline'.lower(),
        'outline'.lower(),
    }

    hits: list[tuple[int, str]] = []
    seen_local: set[str] = set()

    # Bound the scan to avoid pathological huge chunks.
    n = min(len(cleaned), int(max_lines))
    for i in range(n):
        cl = cleaned[i]
        if not cl:
            continue
        key_l = cl.strip().lower()
        if key_l in skip:
            continue

        # 1) "Quiz-ready" marker: previous non-empty line is typically the title.
        if key_l == 'quiz-ready':
            maybe = _maybe_title_from_quiz_ready(cleaned, i)
            if maybe:
                j, title = maybe
                k = _clean_line(title).lower()
                if k and k not in seen_local:
                    seen_local.add(k)
                    hits.append((int(j), title[:255]))
            continue

        # 2) Explicit topic headings (Chủ đề/Phụ lục/Chương/Mục...)
        if _is_topic_heading(cl) and not _is_bad_heading_candidate(cl):
            k = _clean_line(cl).lower()
            if k and k not in seen_local:
                seen_local.add(k)
                hits.append((int(i), cl[:255]))
            continue

        # 3) Soft subject headings (title-like lines followed by markers like "Ít dữ liệu" / "Ý chính" / ...)
        if _is_soft_topic_heading(cl, cleaned, i):
            k = _clean_line(cl).lower()
            if k and k not in seen_local:
                seen_local.add(k)
                hits.append((int(i), cl[:255]))

    return sorted(hits, key=lambda x: x[0])



def _headings_in_chunk_toc(text: str, *, max_lines: int = 500, in_toc: bool = False) -> tuple[list[tuple[int, str]], bool]:
    """Like _headings_in_chunk but skips headings inside Table of Contents regions.

    Returns (hits, in_toc_after).
    """
    if not text:
        return ([], in_toc)

    raw_lines = [ln for ln in (text or '').replace('\r', '').split('\n')]
    cleaned = [_clean_line(ln) for ln in raw_lines]

    skip = {
        'topic outline (học & ra đề)'.lower(),
        'topic outline'.lower(),
        'outline'.lower(),
    }

    hits: list[tuple[int, str]] = []
    seen_local: set[str] = set()

    n = min(len(cleaned), int(max_lines))
    for i in range(n):
        cl = cleaned[i]
        if not cl:
            continue

        # TOC state machine
        if _TOC_START_RX.match(cl):
            in_toc = True
            continue
        if in_toc and _TOC_END_RX.match(cl):
            in_toc = False
            continue
        if in_toc:
            continue

        key_l = cl.strip().lower()
        if key_l in skip:
            continue

        if key_l == 'quiz-ready':
            maybe = _maybe_title_from_quiz_ready(cleaned, i)
            if maybe:
                j, title = maybe
                k = _clean_line(title).lower()
                if k and k not in seen_local:
                    seen_local.add(k)
                    hits.append((int(j), title[:255]))
            continue

        if _is_topic_heading(cl) and not _is_bad_heading_candidate(cl):
            k = _clean_line(cl).lower()
            if k and k not in seen_local:
                seen_local.add(k)
                hits.append((int(i), cl[:255]))
            continue

        if _is_soft_topic_heading(cl, cleaned, i):
            k = _clean_line(cl).lower()
            if k and k not in seen_local:
                seen_local.add(k)
                hits.append((int(i), cl[:255]))

    return (sorted(hits, key=lambda x: x[0]), in_toc)


def _extract_by_headings_in_chunks(chunks_texts: List[str]) -> List[Dict[str, Any]]:
    """Chunk-aware topic extraction.

    This aims to give stable start/end chunk indexes so each topic "covers all" the content
    between two headings.
    """
    if not chunks_texts:
        return []

    # Detect starts (allow multiple headings within one chunk)
    starts: list[tuple[int, int, str]] = []  # (chunk_index, line_idx, title)
    prev_key: tuple[int, str] | None = None
    seen_start_keys: set[tuple[int, str, int]] = set()
    in_toc = False
    # Helper: last non-empty line index + text in a chunk (for cross-chunk "Quiz-ready" splits).
    def _last_non_empty_line(tx: str) -> tuple[int, str] | None:
        if not tx:
            return None
        raw_lines = [ln for ln in tx.replace('\r','').split('\n')]
        cleaned = [_clean_line(ln) for ln in raw_lines]
        for i in range(len(cleaned) - 1, -1, -1):
            if cleaned[i] and cleaned[i].strip():
                return (i, cleaned[i])
        return None

    for ci, tx in enumerate(chunks_texts):
        # Scan deeper to avoid missing headings that appear later in a chunk.
        hits, in_toc = _headings_in_chunk_toc(tx, max_lines=500, in_toc=in_toc)

        # Cross-chunk case: chunk begins with "Quiz-ready" but the title was in the previous chunk.
        # This happens when we chunk by characters and the cut lands between the title line and the marker.
        if ci > 0 and tx:
            raw_lines = [ln for ln in tx.replace('\r','').split('\n')]
            cleaned = [_clean_line(ln) for ln in raw_lines]
            non_empty_idx = [i for i, x in enumerate(cleaned) if x and x.strip()][:8]
            if non_empty_idx:
                first_qr = next((i for i in non_empty_idx if cleaned[i].strip().lower() == 'quiz-ready'), None)
                if first_qr is not None:
                    any_above = any(i < first_qr for i in non_empty_idx)
                    if not any_above:
                        prev = _last_non_empty_line(chunks_texts[ci - 1] or '')
                        if prev:
                            pli, ptitle = prev
                            if ptitle and (not _looks_like_question_item(ptitle)) and (not _is_bad_heading_candidate(ptitle)):
                                norm = _clean_line(ptitle).lower()
                                key2 = (int(ci - 1), norm, int(pli))
                                if norm and key2 not in seen_start_keys:
                                    seen_start_keys.add(key2)
                                    starts.append((int(ci - 1), int(pli), str(ptitle)[:255]))

        if not hits:
            continue
        for line_idx, title in hits:
            # skip very generic headings
            if title.strip().lower() in {'mục lục', 'table of contents', 'contents'}:
                continue
            if _is_bad_heading_candidate(title):
                continue
            key = (ci, _clean_line(title).lower())
            # avoid accidental duplicates inside the same chunk
            if prev_key and prev_key[0] == ci and prev_key[1] == key[1]:
                continue
            prev_key = key
            k3 = (int(ci), key[1], int(line_idx))
            if key[1] and k3 not in seen_start_keys:
                seen_start_keys.add(k3)
                starts.append((ci, int(line_idx), title))

    starts = sorted(starts, key=lambda x: (x[0], x[1]))

    # If we detect at least one heading, we can build at least one topic.
    if len(starts) < 1:
        return []

    # Avoid TOC-like false positives: too many starts over very small amount of text
    if len(starts) >= 18 and len(chunks_texts) < 240:
        return []

    topics: List[Dict[str, Any]] = []
    for j, (start_ci, start_li, title) in enumerate(starts):
        # end position is right BEFORE the next heading (which can be inside the same chunk)
        if j + 1 < len(starts):
            next_ci, next_li, _ = starts[j + 1]
            end_ci = int(next_ci)
            end_li = int(next_li) - 1
        else:
            end_ci = int(len(chunks_texts) - 1)
            end_li = None

        if end_ci < start_ci:
            continue

        body_parts: list[str] = []
        for ci in range(int(start_ci), int(end_ci) + 1):
            tx = chunks_texts[ci] or ''
            raw_lines = [ln for ln in tx.replace('\r', '').split('\n')]

            if ci == int(start_ci):
                from_i = int(start_li) + 1
            else:
                from_i = 0

            if ci == int(end_ci) and end_li is not None:
                to_i = max(from_i, int(end_li) + 1)
            else:
                to_i = len(raw_lines)

            seg = "\n".join(raw_lines[from_i:to_i]).strip()
            if seg:
                body_parts.append(seg)

        body = ('\n\n'.join([b for b in body_parts if b and b.strip()])).strip()
        # Keep smaller topics too; they may be valid but just not "quiz-ready".
        # Allow smaller sections in "ít dữ liệu" docs; quiz readiness is handled separately.
        if len(re.sub(r'\s+', ' ', body)) < 35:
            continue

        topics.append(
            {
                'title': title,
                'body': body,
                'start_chunk_index': int(start_ci),
                'end_chunk_index': int(end_ci),
            }
        )

    # Do NOT auto-merge by body length: it causes topics to "dính" nhau.
    # We only merge when the title itself looks like noise.
    merged: List[Dict[str, Any]] = []
    for t in topics:
        if not merged:
            merged.append(t)
            continue
        title = str(t.get('title') or '').strip()
        body = str(t.get('body') or '').strip()
        if (len(body) < 160) and (_is_bad_heading_candidate(title) or _is_generic_title(title)):
            merged[-1]['body'] = (merged[-1].get('body') or '') + '\n\n' + title + '\n' + body
            merged[-1]['end_chunk_index'] = t.get('end_chunk_index')
            continue
        merged.append(t)

    return merged


def _extract_outline(text: str, *, limit: int = 28) -> List[str]:
    lines = [ln for ln in (text or '').replace('\r', '').split('\n')]
    out: list[str] = []
    for ln in lines:
        cl = _clean_line(ln)
        if not cl:
            continue
        if _is_heading(cl):
            if cl not in out:
                out.append(cl[:255])
        if len(out) >= limit:
            break
    return out


def _extract_bullets_and_steps(text: str, *, limit: int = 18) -> List[str]:
    lines = [ln.rstrip() for ln in (text or '').replace('\r', '').split('\n')]
    out: list[str] = []
    rx = re.compile(r'^\s*(?:[\-•\*]+\s+|\d{1,2}[\)\.\:]\s+|bước\s*\d+\s*[:\-]?\s+|step\s*\d+\s*[:\-]?\s+)', re.IGNORECASE)
    for ln in lines:
        if not ln.strip():
            continue
        if rx.match(ln):
            cl = _clean_line(ln)
            # Avoid pulling exercise prompts / MCQ options into "Ý chính".
            if _looks_like_question_item(cl) or _is_mcq_choices_line(cl) or _is_answer_key_line(cl):
                continue
            if len(cl) >= 6 and cl not in out:
                out.append(cl[:280])
        if len(out) >= limit:
            break
    return out


def _extract_examples(text: str, *, limit: int = 10) -> List[str]:
    sents = _sentences(text)
    out: list[str] = []
    for s in sents:
        sl = s.lower()
        if any(k in sl for k in ['ví dụ', 'vd:', 'vd.', 'chẳng hạn', 'example']):
            ss = s.strip()
            if len(ss) > 420:
                ss = ss[:417].rstrip() + '…'
            if ss and ss not in out:
                out.append(ss)
        if len(out) >= limit:
            break
    return out


def _extract_formulas(text: str, *, limit: int = 10) -> List[str]:
    lines = [ln.strip() for ln in (text or '').replace('\r', '').split('\n')]
    out: list[str] = []
    for ln in lines:
        if not ln:
            continue
        if len(ln) > 220:
            continue
        # simple heuristic: equation-like line
        if ('=' in ln or '→' in ln or '->' in ln) and any(ch.isdigit() for ch in ln):
            if ln not in out:
                out.append(ln)
        if len(out) >= limit:
            break
    return out


def _extract_definitions(text: str, *, limit: int = 14) -> List[Dict[str, str]]:
    """Best-effort definition extraction.

    Returns list of {term, definition}.
    """
    out: list[dict[str, str]] = []

    # 1) colon definitions: "Thuật ngữ: định nghĩa"
    lines = [ln.strip() for ln in (text or '').replace('\r', '').split('\n')]
    rx_colon = re.compile(r'^(.{2,60})\s*[:：]\s*(.{6,260})$')
    for ln in lines:
        m = rx_colon.match(ln)
        if not m:
            continue
        term = _clean_line(m.group(1))
        defi = m.group(2).strip()
        if 2 <= len(term.split()) <= 10 and len(defi) >= 6:
            out.append({'term': term[:80], 'definition': defi[:320]})
        if len(out) >= limit:
            return out

    # 2) sentence pattern: "X là Y"
    sents = _sentences(text)
    rx_la = re.compile(r'^(.{2,80})\s+là\s+(.{6,260})$', re.IGNORECASE)
    for s in sents:
        ss = s.strip()
        if len(ss) < 18 or len(ss) > 360:
            continue
        m = rx_la.match(ss)
        if not m:
            continue
        term = _clean_line(m.group(1))
        defi = m.group(2).strip()
        if 1 <= len(term.split()) <= 8 and len(defi.split()) >= 4:
            out.append({'term': term[:80], 'definition': defi[:320]})
        if len(out) >= limit:
            break

    # De-dup by term
    dedup: list[dict[str, str]] = []
    seen = set()
    for d in out:
        key = d.get('term','').lower()
        if not key or key in seen:
            continue
        seen.add(key)
        dedup.append(d)
    return dedup[:limit]


def build_topic_details(body: str, *, title: str = '') -> Dict[str, Any]:
    """Create a "topic is complete" profile from its body (no hallucination)."""
    outline = _extract_outline(body)
    bullets = _extract_bullets_and_steps(body)
    examples = _extract_examples(body)
    formulas = _extract_formulas(body)
    definitions = _extract_definitions(body)

    # key points: bullets + some informative sentences
    key_points: list[str] = []
    for b in bullets:
        if b not in key_points:
            key_points.append(b)
    if len(key_points) < 12:
        sents = _sentences(body)
        cues = ['gồm', 'bao gồm', 'đặc điểm', 'ưu điểm', 'nhược điểm', 'quy trình', 'các bước', 'lưu ý', 'nhớ rằng', 'cần']
        for s in sents:
            sl = s.lower()
            if any(c in sl for c in cues):
                ss = s.strip()
                if len(ss) > 420:
                    ss = ss[:417].rstrip() + '…'
                if ss and ss not in key_points:
                    key_points.append(ss)
            if len(key_points) >= 14:
                break

    # remove title repeated in outline
    if title:
        outline = [o for o in outline if _clean_line(o).lower() != _clean_line(title).lower()]

    # Minimal Study Guide fallback (no LLM): always include
    # theory + 3 difficulty exercises + quick check.
    sg_lines: list[str] = []
    guide_title = title.strip() or "Chủ đề"
    sg_lines.append(f"# {guide_title}")
    if key_points:
        sg_lines.append(f"_{'; '.join(key_points[:2])[:260]}._")

    sg_lines.append("\n## 📚 Nội dung cốt lõi")
    sg_lines.append("### Khái niệm chính")
    if definitions:
        for d in definitions[:8]:
            term = str(d.get('term') or '').strip()
            defi = str(d.get('definition') or '').strip()
            if term and defi:
                sg_lines.append(f"- **{term}**: {defi}")
    else:
        for kp in key_points[:4]:
            sg_lines.append(f"- {kp}")

    sg_lines.append("### Điểm cần nhớ")
    for kp in (key_points[:10] or bullets[:10]):
        sg_lines.append(f"- {kp}")

    sg_lines.append("### Ví dụ minh họa")
    for ex in (examples[:4] or ["Ôn lại một ví dụ điển hình trong tài liệu và giải thích vì sao kết quả đúng."]):
        sg_lines.append(f"- {ex}")

    sg_lines.append("\n## ✏️ Bài tập luyện tập")
    sg_lines.append("### 🟢 Dễ (3-5 câu — nhớ/hiểu)")
    for i, d in enumerate(definitions[:4], 1):
        term = str(d.get('term') or '').strip()
        defi = str(d.get('definition') or '').strip()
        if not term or not defi:
            continue
        gap = term[:1] + "_" * max(3, min(8, len(term) - 1))
        sg_lines.append(f"{i}. Điền vào chỗ trống: \"{gap} là {defi}\".")
        sg_lines.append(f"   *(Đáp án: {term})*")
    if len(definitions) == 0:
        for i, kp in enumerate(key_points[:3], 1):
            sg_lines.append(f"{i}. Câu nào mô tả đúng ý sau: \"{kp}\"?")
            sg_lines.append("   A. Đúng hoàn toàn  B. Đúng một phần  C. Không liên quan  D. Sai")
            sg_lines.append("   *(Đáp án: A)*")

    sg_lines.append("### 🟡 Trung bình (3-5 câu — áp dụng)")
    for i, ex in enumerate((examples[:4] or key_points[:4]), 1):
        sg_lines.append(f"{i}. Dựa vào ví dụ sau, hãy nêu cách áp dụng tương tự trong tình huống khác: {ex}")
        sg_lines.append("   *(Đáp án gợi ý: Nêu đúng bước làm và lý do lựa chọn.)*")

    sg_lines.append("### 🔴 Khó (2-3 câu — phân tích/đánh giá)")
    hard_seeds = key_points[:3] or bullets[:3]
    for i, kp in enumerate(hard_seeds, 1):
        sg_lines.append(f"{i}. Phân tích điểm mạnh/yếu của nhận định sau và đề xuất cải tiến: \"{kp}\".")
        sg_lines.append("   *(Hướng dẫn: so sánh, nêu tiêu chí đánh giá và kết luận có lập luận.)*")

    sg_lines.append("\n## 🎯 Kiểm tra nhanh (10 câu trắc nghiệm)")
    sg_lines.append("*(Thời gian: 10 phút — KHÔNG có đáp án trong study guide, xem kết quả sau khi nộp)*")
    qc_seeds = key_points[:10] or bullets[:10]
    for i in range(10):
        seed = qc_seeds[i % len(qc_seeds)] if qc_seeds else f"Nội dung cốt lõi {i+1}"
        sg_lines.append(f"{i+1}. Phát biểu nào đúng nhất về: {seed}?")
        sg_lines.append("   A. Phát biểu đúng theo tài liệu")
        sg_lines.append("   B. Phát biểu gần đúng nhưng thiếu điều kiện")
        sg_lines.append("   C. Phát biểu sai")
        sg_lines.append("   D. Không thể kết luận")

    sg_lines.append("\n## ⚠️ Lỗi thường gặp")
    for m in (key_points[:5] or ["Nhớ nhầm khái niệm giữa các thuật ngữ gần giống nhau."]):
        sg_lines.append(f"- Dễ nhầm khi học phần: {m}")

    return {
        'outline': outline[:28],
        'key_points': key_points[:14],
        'definitions': definitions[:14],
        'examples': examples[:10],
        'formulas': formulas[:10],
        'study_guide_md': "\n".join(sg_lines).strip(),
    }


def _llm_topic_details(body: str, *, title: str) -> Optional[Dict[str, Any]]:
    """LLM-enrich topic details, grounded to the given body.

    Returns JSON dict or None.
    """
    if not llm_available():
        return None
    # Feed the model a cleaned + partially repaired version.
    # Keep newlines so the model can infer structure and rewrite OCR-broken words.
    text = clean_topic_text_for_display(body or '')
    try:
        text = repair_ocr_spacing_text(text)
    except Exception:
        pass
    try:
        text = _normalize_vn_pairs(text)
    except Exception:
        pass
    text = (text or '').replace('\r', '').strip()
    if len(re.sub(r"\s+", " ", text)) < 900:
        return None
    excerpt = "\n".join(text.split('\n')[:420]).strip()[:9000]

    try:
        outline_hint = _extract_outline(text)[:14]
    except Exception:
        outline_hint = []
    outline_txt = "\n".join([f"- {x}" for x in outline_hint if str(x).strip()])

    system = (
        "Bạn là giáo viên. Hãy tạo 'Study Guide' giống phong cách Thea (ngắn gọn, dễ học, có ví dụ), "
        "dựa CHỈ trên nội dung được cung cấp. Không bịa, không thêm kiến thức ngoài. "
        "QUAN TRỌNG: Văn bản đầu vào có lỗi OCR về khoảng trắng/tách-dính từ. "
        "Bạn PHẢI tự sửa để viết tiếng Việt mượt mà. Ví dụ: 'thự chiện'→'thực hiện', 'máytính'→'máy tính', 'ngônngữ'→'ngôn ngữ', 'phiê nbản'→'phiên bản'. "
        "Trả JSON hợp lệ theo schema: {summary, keywords, outline, learning_objectives, core_concepts, key_definitions, important_formulas, worked_examples, common_mistakes, practical_applications, study_guide_md, self_check}.  "
        "Yêu cầu:\n"
        "- Viết bằng tiếng Việt, không nhắc tới AI/prompt/JSON/schema.\n"
        "- summary: 2-4 câu, giải thích topic là gì.\n"
        "- keywords: 8-14 từ khóa.\n"
        "- outline: 4-12 mục con (nếu có).\n"
        "- key_points: 10-16 ý chính bao quát.\n"
        "- definitions: 5-14 khái niệm quan trọng [{term, definition}].\n"
        "- examples: 2-8 ví dụ ngắn (có thể có code 1-3 dòng nếu phù hợp).\n"
        "- formulas: 0-6 dòng công thức/biểu thức nếu có.\n"
        "- study_guide_md: Markdown, cấu trúc gợi ý (giống Thea):\n"
        "  ## <Tiêu đề>\n  <1 đoạn giải thích>\n  ### Ý chính\n  - ...\n  ### Ví dụ\n  ```\n  ...\n  ```\n  ### Lưu ý/Lỗi thường gặp\n  - ...\n  (Giữ 250-600 từ, ưu tiên rõ ràng, đúng nội dung).\n"
        "- self_check: 5-8 câu hỏi tự kiểm tra (không cần đáp án).\n"
        "- Nếu có mục con gợi ý, hãy nhóm nội dung theo mục đó."
    )
    user = (
        f"TIÊU ĐỀ TOPIC: {title}\n\n"
        f"MỤC CON GỢI Ý (nếu có):\n{outline_txt}\n\n"
        f"NỘI DUNG TOPIC (đã làm sạch, trích):\n{excerpt}"
    )
    try:
        obj = chat_json(
            messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
            temperature=0.15,
            max_tokens=900,
        )
        if not isinstance(obj, dict):
            return None
        # light normalization
        out: Dict[str, Any] = {}
        out['summary'] = str(obj.get('summary') or '').strip()
        kws = obj.get('keywords') if isinstance(obj.get('keywords'), list) else []
        out['keywords'] = [str(x).strip().lower() for x in kws if str(x).strip()][:14]
        out['outline'] = [_clean_line(str(x))[:255] for x in (obj.get('outline') or []) if str(x).strip()][:18] if isinstance(obj.get('outline'), list) else []
        out['key_points'] = [_clean_line(str(x))[:420] for x in (obj.get('key_points') or []) if str(x).strip()][:14] if isinstance(obj.get('key_points'), list) else []

        # New Phase-1 fields (best-effort; backward-compatible)
        objs = obj.get('learning_objectives') if isinstance(obj.get('learning_objectives'), list) else []
        out['learning_objectives'] = [_clean_line(str(x))[:220] for x in objs if str(x).strip()][:10]
        core = obj.get('core_concepts') if isinstance(obj.get('core_concepts'), list) else []
        if not core:
            core = obj.get('key_points') if isinstance(obj.get('key_points'), list) else []
        out['core_concepts'] = [_clean_line(str(x))[:320] for x in core if str(x).strip()][:16]
        mistakes = obj.get('common_mistakes') if isinstance(obj.get('common_mistakes'), list) else []
        out['common_mistakes'] = [_clean_line(str(x))[:320] for x in mistakes if str(x).strip()][:12]
        apps = obj.get('practical_applications') if isinstance(obj.get('practical_applications'), list) else []
        out['practical_applications'] = [_clean_line(str(x))[:320] for x in apps if str(x).strip()][:12]

        defs = obj.get('definitions') if isinstance(obj.get('definitions'), list) else []
        norm_defs: list[dict[str,str]] = []
        for d in defs:
            if not isinstance(d, dict):
                continue
            term = _clean_line(str(d.get('term') or ''))
            defi = _clean_line(str(d.get('definition') or ''))
            if term and defi:
                norm_defs.append({'term': term[:80], 'definition': defi[:320]})
        out['definitions'] = norm_defs[:16]
        # key_definitions: allow model to override; otherwise reuse definitions
        kd = obj.get('key_definitions') if isinstance(obj.get('key_definitions'), list) else []
        norm_kd: list[dict[str, str]] = []
        for d in kd:
            if not isinstance(d, dict):
                continue
            term = _clean_line(str(d.get('term') or ''))
            defi = _clean_line(str(d.get('definition') or ''))
            if term and defi:
                norm_kd.append({'term': term[:80], 'definition': defi[:320]})
        out['key_definitions'] = (norm_kd[:16] if norm_kd else norm_defs[:16])
        out['examples'] = [str(x).strip()[:420] for x in (obj.get('examples') or []) if str(x).strip()][:10] if isinstance(obj.get('examples'), list) else []
        out['formulas'] = [str(x).strip()[:220] for x in (obj.get('formulas') or []) if str(x).strip()][:10] if isinstance(obj.get('formulas'), list) else []
        sg = obj.get('study_guide_md')
        if isinstance(sg, str) and sg.strip():
            out['study_guide_md'] = sg.strip()[:9000]
        sc = obj.get('self_check')
        if isinstance(sc, list):
            out['self_check'] = [str(x).strip()[:260] for x in sc if str(x).strip()][:10]
        return out
    except Exception:
        return None


def enrich_topic_details_with_llm(body: str, *, title: str) -> Dict[str, Any]:
    """Public wrapper to optionally enrich a topic body with Thea-like study guide fields."""
    det = _llm_topic_details(body, title=title)
    out = det if isinstance(det, dict) else {}

    # Optional: generate a higher-quality Markdown study guide using plain-text generation.
    # This avoids strict JSON-mode brittleness on some OpenAI-compatible servers.
    mode = (getattr(settings, 'TOPIC_STUDY_GUIDE_MODE', 'json') or 'json').strip().lower()
    if mode in ('text', 'markdown', 'md'):
        try:
            guide = generate_study_guide_md(body, title=title)
            if guide:
                out['study_guide_md'] = guide
        except Exception:
            pass
    return out


def extract_exercises_from_topic(topic_text: str, topic_title: str) -> list[dict]:
    """Dùng LLM để trích xuất bài tập gốc từ đoạn text của topic."""
    if not llm_available() or not topic_text:
        return []

    prompt = f'''Đoạn văn bản sau là nội dung topic "{topic_title}" từ sách giáo khoa.
    Hãy tìm và trích xuất TẤT CẢ bài tập, câu hỏi ôn tập có trong đoạn này.
    Trả về JSON array, mỗi phần tử có:
    - "type": "mcq" hoặc "essay" hoặc "exercise"
    - "question": nội dung câu hỏi/bài tập (giữ nguyên từ sách)
    - "options": ["A", "B", "C", "D"] nếu là MCQ, null nếu không
    - "answer": đáp án nếu có trong sách, null nếu không
    - "source": "original_pdf"
    Nếu không có bài tập nào, trả về [].
    Văn bản: {topic_text[:3000]}'''
    try:
        result = chat_json(messages=[{"role": "user", "content": prompt}], max_tokens=1500)
        if not isinstance(result, list):
            return []

        out: list[dict] = []
        for item in result:
            if not isinstance(item, dict):
                continue
            q = str(item.get("question") or "").strip()
            if not q:
                continue
            q_type = str(item.get("type") or "exercise").strip().lower()
            if q_type not in {"mcq", "essay", "exercise"}:
                q_type = "exercise"
            options = item.get("options")
            if not isinstance(options, list):
                options = None
            else:
                options = [str(x).strip() for x in options if str(x).strip()][:8] or None
            ans = item.get("answer")
            answer = str(ans).strip() if ans is not None and str(ans).strip() else None
            out.append(
                {
                    "type": q_type,
                    "question": q,
                    "options": options,
                    "answer": answer,
                    "source": "original_pdf",
                }
            )
        return out
    except Exception:
        return []


def generate_study_guide_md(body: str, *, title: str) -> str:
    """Generate a Thea-like Markdown study guide from a topic body.

    This function is designed to:
    - rewrite OCR-broken text into clean Vietnamese
    - structure content for learning + homework + quick tests
    """
    if not llm_available():
        return ""

    text = clean_topic_text_for_display(body or '')
    try:
        text = repair_ocr_spacing_text(text)
    except Exception:
        pass
    try:
        text = _normalize_vn_pairs(text)
    except Exception:
        pass
    text = (text or '').strip()
    if len(re.sub(r"\s+", " ", text)) < 900:
        return ""

    outline_hint = []
    try:
        outline_hint = _extract_outline(text)[:16]
    except Exception:
        outline_hint = []
    outline_txt = "\n".join([f"- {x}" for x in outline_hint if str(x).strip()])

    excerpt = "\n".join(text.split('\n')[:520]).strip()[:11000]

    system = (
        "Bạn là giáo viên THPT. Nhiệm vụ: Tạo TÀI LIỆU HỌC TẬP HOÀN CHỈNH cho 1 topic. "
        "Dựa CHỈ trên nội dung được cung cấp. Không bịa thêm kiến thức. "
        "Sửa lỗi OCR: 'thự chiện'→'thực hiện', 'lậptrình'→'lập trình'. "
        "Xuất DUY NHẤT Markdown. KHÔNG JSON, KHÔNG giải thích ngoài lề. "
        "CẤU TRÚC BẮT BUỘC (ĐỦ 5 PHẦN, KHÔNG THIẾU):\n\n"
        "# {title}\n"
        "_{tóm tắt 2-3 câu, nêu trọng tâm topic}_\n\n"
        "## 📚 Nội dung cốt lõi\n"
        "### Khái niệm chính\n"
        "- [Khái niệm 1]: [định nghĩa ngắn gọn]\n"
        "- [Khái niệm 2]: ...\n"
        "### Điểm cần nhớ\n"
        "- [Ý quan trọng 1]\n"
        "- [8-12 ý chính]\n"
        "### Ví dụ minh họa\n"
        "[2-4 ví dụ cụ thể từ tài liệu]\n\n"
        "## ✏️ Bài tập luyện tập\n"
        "### 🟢 Dễ (3-5 câu — nhớ/hiểu)\n"
        "1. [Câu hỏi trắc nghiệm/điền]\n"
        "   A. ... B. ... C. ... D. ...\n"
        "   *(Đáp án: X)*\n"
        "### 🟡 Trung bình (3-5 câu — áp dụng)\n"
        "1. [Câu hỏi tình huống]\n"
        "   *(Đáp án gợi ý: ...)*\n"
        "### 🔴 Khó (2-3 câu — phân tích/đánh giá)\n"
        "1. [Câu hỏi phân tích/so sánh]\n"
        "   *(Hướng dẫn: ...)*\n\n"
        "## 🎯 Kiểm tra nhanh (10 câu trắc nghiệm)\n"
        "*(Thời gian: 10 phút — KHÔNG có đáp án trong study guide, xem kết quả sau khi nộp)*\n"
        "1. [Câu 1 — dễ]\n   A. ... B. ... C. ... D. ...\n"
        "[... đến câu 10]\n\n"
        "## ⚠️ Lỗi thường gặp\n"
        "- [Nhầm lẫn phổ biến 1]\n"
        "- [4-6 lỗi/nhầm lẫn hay gặp]\n"
    )
    user = (
        f"TIÊU ĐỀ TOPIC: {title}\n\n"
        f"MỤC CON GỢI Ý (nếu có):\n{outline_txt}\n\n"
        f"NỘI DUNG TOPIC (đã làm sạch, trích):\n{excerpt}"
    )

    txt = chat_text(
        messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
        temperature=0.2,
        max_tokens=1500,
    )
    if not isinstance(txt, str):
        return ""
    t = txt.strip()
    # strip accidental fences
    t = re.sub(r"^```[a-zA-Z]*\n", "", t)
    t = re.sub(r"\n```\s*$", "", t)
    return t.strip()[:14000]


def parse_quick_check_quiz(study_guide_md: str) -> list[dict[str, Any]]:
    """Extract 10 MCQ questions from the 'Kiểm tra nhanh' section in markdown."""
    text = str(study_guide_md or "").replace("\r", "")
    if not text.strip():
        return []

    sec_match = re.search(
        r"##\s*🎯\s*Kiểm\s*tra\s*nhanh.*?(?=\n##\s|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    section = sec_match.group(0) if sec_match else text
    lines = [ln.rstrip() for ln in section.split("\n")]

    q_rx = re.compile(r"^\s*(\d{1,2})[\.)]\s+(.+?)\s*$")
    opt_rx = re.compile(r"^\s*([ABCD])[\.)]\s+(.+?)\s*$", flags=re.IGNORECASE)
    out: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None

    for ln in lines:
        q_m = q_rx.match(ln)
        if q_m:
            if cur and len(cur.get("options") or []) >= 2:
                out.append(cur)
            cur = {"stem": q_m.group(2).strip(), "options": []}
            continue
        if not cur:
            continue
        # handle one-line options "A. ... B. ..."
        inline = re.findall(r"([ABCD])[\.)]\s*([^ABCD]{1,220}?)(?=(?:\s+[ABCD][\.)])|$)", ln)
        if inline and len(inline) >= 2:
            for _, opt in inline[:4]:
                opt_clean = _clean_line(opt)
                if opt_clean:
                    cur["options"].append(opt_clean[:220])
            continue
        o_m = opt_rx.match(ln)
        if o_m:
            cur["options"].append(_clean_line(o_m.group(2))[:220])

    if cur and len(cur.get("options") or []) >= 2:
        out.append(cur)

    norm: list[dict[str, Any]] = []
    for it in out:
        stem = str(it.get("stem") or "").strip()
        options = [str(x).strip() for x in (it.get("options") or []) if str(x).strip()][:4]
        if stem and len(options) >= 2:
            while len(options) < 4:
                options.append("Không có đáp án phù hợp")
            norm.append({"stem": stem[:420], "options": options[:4]})
        if len(norm) >= 10:
            break
    return norm



def extract_exercises_from_topic(topic_text: str, topic_title: str) -> list[dict[str, str]]:
    """Trích xuất bài tập gốc từ nội dung topic bằng LLM (best-effort)."""

    text = str(topic_text or "").strip()
    title = str(topic_title or "").strip() or "Chủ đề"
    if not text or not llm_available():
        return []

    excerpt = "\n".join(text.splitlines()[:180])[:8000]
    system = (
        "Bạn là trợ lý học tập. Hãy trích xuất CÁC BÀI TẬP GỐC xuất hiện trong nội dung, "
        "không tự tạo thêm. Trả JSON array, mỗi phần tử gồm: question, answer_hint. "
        "Nếu không thấy bài tập thì trả []"
    )
    user = {
        "topic_title": title,
        "topic_text_excerpt": excerpt,
    }

    try:
        obj = chat_json(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.0,
            max_tokens=700,
        )
    except Exception:
        return []

    if isinstance(obj, dict):
        obj = obj.get("exercises")
    if not isinstance(obj, list):
        return []

    out: list[dict[str, str]] = []
    for it in obj:
        if not isinstance(it, dict):
            continue
        q = str(it.get("question") or "").strip()
        h = str(it.get("answer_hint") or "").strip()
        if q:
            out.append({"question": q[:500], "answer_hint": h[:300]})
        if len(out) >= 20:
            break
    return out

def extract_topics(
    full_text: str,
    *,
    chunks_texts: Optional[List[str]] = None,
    heading_level: str | None = None,
    max_topics: int = 12,
    min_quality: float = 0.35,
    include_details: bool = True,
    max_body_preview: int = 1600,
    max_llm_topics: int = 6,
) -> Dict[str, Any]:
    """Extract a topic list from document text.

    Mục tiêu: 1 topic phải "đầy đủ" (bao trọn) nội dung thuộc topic đó.

    Returns:
      {"status": "OK"|"NEED_CLEAN_TEXT", "topics": [...], "quality": {...}}

    Each topic includes (when OK):
      title, summary, keywords, body_len,
      start_chunk_index?, end_chunk_index?,
      outline, key_points, definitions, examples, formulas,
      content_preview, content_len, has_more_content

    NOTE: content_preview is bounded; full content can be reconstructed later from chunks by (start_chunk_index,end_chunk_index).
    """

    try:
        from app.services.vietnamese_font_fix import (
            detect_broken_vn_font,
            fix_vietnamese_font_encoding,
        )
        if full_text and detect_broken_vn_font(full_text):
            full_text = fix_vietnamese_font_encoding(full_text)
        if chunks_texts:
            chunks_texts = [
                fix_vietnamese_font_encoding(c) if detect_broken_vn_font(c or "") else (c or "")
                for c in chunks_texts
            ]
    except ImportError:
        pass

    full_text = full_text or ""

    # Repair common PDF/OCR spacing artifacts before any splitting/quality checks.
    try:
        full_text = repair_ocr_spacing_text(full_text or "")
    except Exception:
        pass
    try:
        full_text = _normalize_vn_pairs(full_text or "")
    except Exception:
        pass

    # Quality guard: allow documents that contain a JSON appendix.
    # Large JSON blocks tend to be symbol-heavy and can incorrectly trip the OCR/garble detector.
    q_text = str(full_text or '')
    q_text = re.sub(r"\{[\s\S]{80,8000}?\}", " ", q_text)
    q_text = re.sub(r"\[[\s\S]{80,8000}?\]", " ", q_text)
    qt = quality_report(q_text)
    # For topic extraction we can be more permissive than quiz generation:
    # even symbol-heavy documents (math formulas, JSON appendices) can still yield correct topic boundaries.
    # We'll only block when BOTH quality is low AND we fail to extract any topics.
    low_quality = qt.get("score", 0.0) < float(min_quality)

    # 1) Split on FULL TEXT first (stable boundaries).
    # Chunk-based splitting is more fragile because chunk boundaries can cut through headings.
    topics_raw: List[Dict[str, Any]] = []
    level = (heading_level or '').strip().lower() or None
    if level == 'chapter':
        topics_raw = _extract_by_chapters(full_text)
    else:
        lesson_mode = _detect_lesson_mode(full_text)
        topics_raw = _extract_by_lessons(full_text) if lesson_mode else _extract_by_headings(full_text)

    # 2) If we have chunks, map topics back to chunk ranges using heading anchors.
    # This yields tight, correct ranges for later topic detail / quiz generation.
    if topics_raw and chunks_texts:
        try:
            ranges = _map_topics_to_chunk_ranges_by_anchors(topics_raw, chunks_texts)
            if ranges and len(ranges) == len(topics_raw):
                for t, (s_idx, e_idx) in zip(topics_raw, ranges):
                    if s_idx is not None and e_idx is not None:
                        t['start_chunk_index'] = int(s_idx)
                        t['end_chunk_index'] = int(e_idx)
        except Exception:
            pass

    # 3) Fallback: chunk-based heading scan only when full-text splitting yielded nothing.
    if not topics_raw and chunks_texts:
        if level == 'chapter':
            topics_raw = _extract_by_chapters_in_chunks(chunks_texts)
        else:
            topics_raw = _extract_by_lessons_in_chunks(chunks_texts) if lesson_mode else _extract_by_headings_in_chunks(chunks_texts)

    # If no headings, optionally ask the LLM to propose a topic outline (grounded to text)
    if not topics_raw and llm_available():
        excerpt = re.sub(r"\s+", " ", (full_text or "")).strip()[:6000]
        if len(excerpt) >= 800:
            level_hint = "Chia theo CHƯƠNG/CHAPTER (các dòng bắt đầu bằng 'Chương'/'Chapter')" if level == 'chapter' else "Chia theo các TOPIC học tập hợp lý"
            system = (
                "Bạn là Content Agent (giáo viên). Nhiệm vụ: chia tài liệu thành các TOPIC học tập rõ ràng. "
                f"YÊU CẦU CHÍNH: {level_hint}. "
                "KHÔNG dùng số thứ tự trong title (ví dụ: 'Topic 1', 'Chương 2', '1.2.3'). "
                "KHÔNG tạo TOPIC riêng cho các mục phụ trợ như: 'Bài tập', 'Luyện tập', 'Câu hỏi', 'Quiz/Mini-quiz', 'Đáp án', 'Lời giải'. "
                "KHÔNG coi các dòng thuộc khối câu hỏi/đề như: 'Q11', 'Câu 12', hoặc các phương án 'A./B./C./D.' là TOPIC. "
                "Nếu gặp các mục đó, hãy gộp nội dung của chúng vào TOPIC học tập ngay trước đó (liên quan nhất). "
                "CHỈ dùng các khái niệm xuất hiện trong văn bản; không bịa thêm nội dung. "
                "QUAN TRỌNG VỀ FORMAT TOPIC:\n"
                "- Tên topic phải là tiếng Việt hoặc tiếng Anh chuẩn, KHÔNG có ký tự lạ hay mã hex\n"
                "- Tên topic phải cụ thể, mô tả đúng nội dung (ví dụ: 'Phương trình bậc hai' thay vì 'Toán học')\n"
                "- Mỗi topic phải có tối thiểu 2-3 đoạn nội dung trong tài liệu\n"
                "- Không tạo topic là phần phụ trợ như 'Bài tập', 'Ví dụ', 'Đáp án'\n"
                "- Output JSON với mảng topics, mỗi topic có: title, summary (2-3 câu), keywords (list)\n"
                "Trả JSON hợp lệ: {topics:[{title, summary, keywords}]} với 5-10 topics. "
                "summary: 2-3 câu, nêu đúng trọng tâm. keywords: 6-10 từ khóa."
            )
            user = f"Văn bản tài liệu (trích): {excerpt}"
            try:
                obj = chat_json(
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    temperature=0.2,
                    max_tokens=900,
                )
                llm_topics = obj.get("topics") if isinstance(obj, dict) else None
                if isinstance(llm_topics, list):
                    topics_raw = post_process_generated_topics(
                        llm_topics[: max(3, int(max_topics))],
                        chunks_texts or [full_text],
                    )
            except Exception:
                topics_raw = []

    if not topics_raw:
        topics_raw = _fallback_segment(full_text)

    # --- Normalize + de-noise raw topics before final formatting ---
    norm_raw: List[Dict[str, Any]] = []
    for t in topics_raw:
        orig_title = str(t.get('title') or '').strip()[:255]
        body = str(t.get('body') or '').strip()
        # "Ít dữ liệu" docs can have short sections; keep them and let quiz-ready guards decide later.
        if not orig_title or len(body) < 20:
            continue

        # Hard filter for obvious OCR/table artifacts accidentally captured as titles.
        if _is_bad_heading_candidate(orig_title):
            continue

        # Remove chapter/section numbering, then remove label prefixes like "Chủ đề:".
        # Optionally keep the "Bài N." prefix for lesson-style documents.
        keep_lesson_prefix = bool(getattr(settings, 'TOPIC_KEEP_LESSON_PREFIX', False))
        keep_chapter_prefix = (level == 'chapter') and (bool(_CHAPTER_ONLY_RX.match(orig_title)) or bool(_TOPLEVEL_SECTIONS_RX.match(orig_title)))
        if keep_chapter_prefix:
            title = orig_title
        elif keep_lesson_prefix and _LESSON_HEADING_RX.match(orig_title):
            title = orig_title
        else:
            title = _strip_topic_numbering(orig_title) or orig_title
        title = _strip_label_prefix(title) or title
        title = _de_all_caps_title(title)[:255]

        # Optionally hide appendix sections from extracted topics (still acts as a boundary).
        is_app = is_appendix_title(title) or is_appendix_title(orig_title)
        if bool(getattr(settings, 'TOPIC_HIDE_APPENDIX', True)) and is_app:
            continue

        if _is_bad_heading_candidate(title):
            continue

        # Clean body for display/summarization.
        body_clean = _clean_topic_body(body)
        if len(re.sub(r"\s+", " ", body_clean)) < 120:
            body_clean = body

        kws = t.get('keywords') if isinstance(t.get('keywords'), list) else None
        if not kws:
            kws = _keywords(body_clean, k=12)

        item: Dict[str, Any] = {
            'title': title[:255],
            'body': body_clean,
            'keywords': [str(x).strip().lower() for x in (kws or []) if str(x).strip()][:16],
        }
        item['is_appendix'] = bool(is_app)
        if t.get('start_chunk_index') is not None:
            item['start_chunk_index'] = int(t.get('start_chunk_index'))
        if t.get('end_chunk_index') is not None:
            item['end_chunk_index'] = int(t.get('end_chunk_index'))
        norm_raw.append(item)

    # Merge duplicates created by noisy outlines before limiting.
    norm_raw = _merge_similar_topics(norm_raw, max_topics=int(max_topics) * 2)


    # Optional LLM filter pass: remove prefaces/TOC artifacts, merge tiny leftovers, rename titles.
    if _topic_llm_filter_enabled():
        try:
            norm_raw = _llm_filter_topics(norm_raw, max_keep=int(max_topics))
        except Exception:
            pass

    # Deterministic merge: ensure every topic is large enough to generate
    # study material + 3 difficulty levels of questions.
    try:
        min_body_chars = int(getattr(settings, 'TOPIC_MIN_BODY_CHARS', 1800) or 1800)
    except Exception:
        min_body_chars = 1800
    norm_raw = _merge_tiny_topics(norm_raw, min_body_chars=min_body_chars)
    # Merge duplicates again after tiny-topic merge.
    norm_raw = _merge_similar_topics(norm_raw, max_topics=int(max_topics) * 2)

    # Limit topics (keep longer ones first if too many)
    if len(norm_raw) > int(max_topics):
        norm_raw = norm_raw[: int(max_topics)]

    out: List[Dict[str, Any]] = []
    llm_used = 0
    llm_title_used = 0
    used_titles: set[str] = set()
    max_llm_titles = max(0, min(int(max_llm_topics), 8))

    for t in norm_raw:
        orig_title = str(t.get('title') or '').strip()[:255]
        title = orig_title
        body = str(t.get('body') or '').strip()
        # Keep shorter sections ("ít dữ liệu"); quiz readiness is handled separately.
        if not title or len(body) < 20:
            continue

        # Optionally rewrite generic/noisy titles using the LLM (grounded to this topic body).
        # This mainly fixes fallback titles like 'Topic 1: kw1, kw2, kw3' which are not teacher-like.
        title_key = title.strip().lower()
        if _topic_title_rewrite_enabled() and llm_title_used < max_llm_titles and _is_generic_title(title):
            cand = _llm_rewrite_title(body, old_title=orig_title)
            if cand:
                cand_key = cand.strip().lower()
                if cand_key and cand_key not in used_titles:
                    title = cand[:255]
                    title_key = cand_key
                    llm_title_used += 1


        # If stripping removed everything (e.g., title was just 'Chương 12'), force a teacher-like title.
        if not title or _is_generic_title(title):
            # Try LLM rewrite first (grounded to body)
            if _topic_title_rewrite_enabled() and llm_title_used < max_llm_titles:
                cand = _llm_rewrite_title(body, old_title=orig_title)
                if cand:
                    title = cand[:255]
                    llm_title_used += 1

        # Final deterministic fallback when LLM not available or didn't help.
        if not title or _is_generic_title(title):
            title = _fallback_teacher_title(body)[:255]

        # Ensure no leading numbering remains after rewrite.
        title2 = _strip_label_prefix(_strip_topic_numbering(title) or title) or title
        title = _de_all_caps_title(title2)[:255]

        # De-duplicate titles WITHOUT adding any index numbers.
        title = _dedupe_title(title, body, used_titles)[:255]
        title_key = title.strip().lower()
        used_titles.add(title_key)

        body_norm = re.sub(r"\s+", " ", body).strip()

        # Split out practice blocks so summaries / key points stay study-focused.
        study_body, practice_body = split_study_and_practice(body)
        body_for_summary = study_body if len(re.sub(r"\s+", " ", study_body)) >= 120 else body
        body_for_details = study_body if study_body else body
        body_norm = re.sub(r"\s+", " ", body_for_summary).strip()
        original_exercises = extract_exercises_from_topic(body, title)

        kws = t.get('keywords') if isinstance(t.get('keywords'), list) else None
        if not kws:
            kws = _keywords(body_for_summary, k=12)

        sents = _sentences(body_for_summary)
        summary = sents[0] if sents else (body_for_summary[:260] if body_for_summary else body[:260])
        summary = summary.strip()
        if len(summary) > 320:
            summary = summary[:317].rstrip() + "…"

        content_preview = body_norm[: int(max_body_preview)]
        has_more = len(body_norm) > int(max_body_preview)

        clean_title, title_warnings = validate_and_clean_topic_title(title)
        needs_review = bool(title_warnings)
        conf = _topic_confidence_score(clean_title or title, body_for_summary)
        if conf < 0.5 or len(re.sub(r"\s+", " ", body_for_summary).strip()) < 120:
            needs_review = True

        item: Dict[str, Any] = {
            "title": clean_title or title,
            "display_title": clean_title or title,
            "needs_review": bool(needs_review),
            "title_warnings": title_warnings,
            "extraction_confidence": conf,
            "summary": summary,
            "keywords": [str(x).strip().lower() for x in (kws or []) if str(x).strip()][:12],
            "body_len": len(body_norm),
            "content_len": len(body_norm),
            "content_preview": content_preview,
            "has_more_content": has_more,
            "body": body,
            "original_exercises": original_exercises,
            "has_original_exercises": bool(original_exercises),
        }

        if practice_body:
            prac_norm = re.sub(r"\s+", " ", practice_body).strip()
            item["practice_len"] = len(prac_norm)
            item["practice_preview"] = prac_norm[: min(900, len(prac_norm))]
            item["has_more_practice"] = len(prac_norm) > 900

        if t.get("start_chunk_index") is not None:
            item["start_chunk_index"] = int(t.get("start_chunk_index"))
        if t.get("end_chunk_index") is not None:
            item["end_chunk_index"] = int(t.get("end_chunk_index"))
        if t.get("page_start") is not None:
            item["page_start"] = int(t.get("page_start"))
        if t.get("page_end") is not None:
            item["page_end"] = int(t.get("page_end"))

        if include_details:
            details = build_topic_details(body_for_details, title=title)
            # LLM enrichment (only for first N topics)
            if llm_available() and llm_used < int(max_llm_topics):
                llm_det = _llm_topic_details(body_for_details, title=title)
                if llm_det:
                    llm_used += 1
                    if llm_det.get('summary'):
                        item['summary'] = str(llm_det.get('summary')).strip()[:420]
                    # prefer LLM parts when present
                    item['outline'] = llm_det.get('outline') or details.get('outline') or []
                    item['key_points'] = llm_det.get('key_points') or details.get('key_points') or []
                    item['definitions'] = llm_det.get('definitions') or details.get('definitions') or []
                    item['examples'] = llm_det.get('examples') or details.get('examples') or []
                    item['formulas'] = llm_det.get('formulas') or details.get('formulas') or []
                    if llm_det.get('study_guide_md'):
                        item['study_guide_md'] = llm_det.get('study_guide_md')
                    if llm_det.get('self_check'):
                        item['self_check'] = llm_det.get('self_check')
                    llm_kws = llm_det.get('keywords') or []
                    if llm_kws:
                        merged: list[str] = []
                        for x in (llm_kws + item['keywords']):
                            xx = str(x).strip().lower()
                            if xx and xx not in merged:
                                merged.append(xx)
                        item['keywords'] = merged[:12]
                else:
                    item.update(details)
            else:
                item.update(details)

            # Optional external enrichment for underspecified/"Ít dữ liệu" topics.
            try:
                if _should_external_enrich(title, body_for_details):
                    lang = (getattr(settings, 'TOPIC_EXTERNAL_WIKI_LANG', 'vi') or 'vi').strip().lower()
                    if _mostly_english(title):
                        lang = 'en'
                    max_src = int(getattr(settings, 'TOPIC_EXTERNAL_MAX_SOURCES', 2) or 2)
                    timeout_sec = int(getattr(settings, 'TOPIC_EXTERNAL_TIMEOUT_SEC', 6) or 6)
                    # Keep query short-ish to improve hit rate.
                    q = " ".join((_WORD_RX.findall(title) or [])[:10]) or title
                    sources = fetch_external_snippets(q, lang=lang, max_sources=max_src, timeout_sec=timeout_sec)
                    if sources:
                        item['sources'] = [
                            {'title': s.get('title') or '', 'url': s.get('url') or '', 'source': s.get('source') or 'external'}
                            for s in sources
                        ]
                        item['external_notes'] = [str(s.get('extract') or '').strip() for s in sources if str(s.get('extract') or '').strip()]
            except Exception:
                # Never fail topic extraction due to optional enrichment.
                pass

        out.append(item)

    evidence_units = _split_evidence_units(full_text, chunks_texts)
    strict_pdf_validation = bool(chunks_texts)
    validated_out: list[dict[str, Any]] = []
    for item in out:
        mentioned_units = [u for u in evidence_units if _unit_mentions_topic(item, u)]
        mention_count = len(mentioned_units)
        if strict_pdf_validation and mention_count < 3:
            # Hard validation for PDF chunks: topic must appear in >=3 chunks.
            continue

        total_units = max(1, len(evidence_units))
        coverage_score = min(1.0, mention_count / total_units)
        if coverage_score >= 0.6:
            confidence = "high"
        elif coverage_score >= 0.3:
            confidence = "medium"
        else:
            confidence = "low"

        sample_content = mentioned_units[0] if mentioned_units else (str(item.get("content_preview") or "").strip())
        sample_content = sample_content[:600]

        item["coverage_score"] = float(round(coverage_score, 4))
        item["confidence"] = confidence
        item["sample_content"] = sample_content
        item["subtopics"] = _derive_subtopics(item)

        ps = item.get("page_start")
        pe = item.get("page_end")
        item["page_ranges"] = [[int(ps), int(pe)]] if ps is not None and pe is not None else []
        validated_out.append(item)

    out = validated_out

    out.sort(key=lambda x: (int(x.get('page_start')) if x.get('page_start') is not None else 10**9,
                            int(x.get('start_chunk_index')) if x.get('start_chunk_index') is not None else 10**9))
    out = _merge_duplicate_topics_by_similarity(out, threshold=0.85)
    out = validate_and_repair_topics(out)

    if not out:
        # Only hard-block when quality is low AND we also failed to extract topics.
        if low_quality:
            return {
                "status": "NEED_CLEAN_TEXT",
                "topics": [],
                "quality": qt,
                "reason": "Tài liệu có vẻ bị OCR lỗi / text rời rạc (hoặc quá nhiều ký hiệu) nên không thể chia topic chắc chắn.",
                "suggestion": "Hãy upload .docx hoặc PDF có text layer / bản copy text (không phải PDF ảnh).",
            }
        return {
            "status": "NEED_CLEAN_TEXT",
            "topics": [],
            "quality": qt,
            "reason": "Không trích xuất được topic đáng tin cậy từ tài liệu.",
            "suggestion": "Hãy upload bản .docx hoặc PDF có text layer rõ ràng hơn.",
        }

    resp = {"status": "OK", "topics": out, "quality": qt}
    if low_quality:
        resp["quality_warning"] = "Text có nhiều ký hiệu (công thức/JSON/bảng) nên độ tin cậy OCR thấp, nhưng vẫn trích xuất được topic."
    return resp



def assign_topic_chunk_ranges(
    topics: List[Dict[str, Any]],
    *,
    chunk_lengths: List[int],
) -> List[Tuple[Optional[int], Optional[int]]]:
    """Assign each topic a (start_chunk_index, end_chunk_index) range.

    This is a best-effort mapping based on relative lengths, kept deterministic.
    """
    n_chunks = len(chunk_lengths)
    if n_chunks <= 0:
        return [(None, None) for _ in topics]

    total_chunk_len = sum(int(x) for x in chunk_lengths)
    topic_lens = [max(1, int(t.get("body_len") or 1)) for t in topics]
    sum_topic = sum(topic_lens)
    if sum_topic <= 0:
        return [(0, n_chunks - 1) for _ in topics]

    # scale topic lengths so their sum ~= chunk lengths
    scale = total_chunk_len / sum_topic
    targets = [max(1, int(round(l * scale))) for l in topic_lens]
    # make last topic absorb rounding leftovers
    diff = total_chunk_len - sum(targets)
    if targets:
        targets[-1] = max(1, targets[-1] + diff)

    ranges: List[Tuple[Optional[int], Optional[int]]] = []
    cur_chunk = 0
    for i, target in enumerate(targets):
        if cur_chunk >= n_chunks:
            ranges.append((None, None))
            continue

        start = cur_chunk
        acc = 0
        while cur_chunk < n_chunks and acc < target:
            acc += int(chunk_lengths[cur_chunk])
            cur_chunk += 1

        end = max(start, cur_chunk - 1)
        # ensure last topic ends at the last chunk
        if i == len(targets) - 1:
            end = n_chunks - 1
        ranges.append((start, end))

    return ranges


def topic_range_stats(
    *,
    start_chunk_index: Optional[int],
    end_chunk_index: Optional[int],
    chunk_lengths: List[int],
) -> Dict[str, int]:
    """Compute (chunk_span, char_len) for a topic range."""
    n = len(chunk_lengths)
    if start_chunk_index is None or end_chunk_index is None or n <= 0:
        return {"chunk_span": 0, "char_len": 0}
    try:
        s = max(0, int(start_chunk_index))
        e = min(n - 1, int(end_chunk_index))
    except Exception:
        return {"chunk_span": 0, "char_len": 0}
    if e < s:
        return {"chunk_span": 0, "char_len": 0}
    span = int(e - s + 1)
    char_len = int(sum(int(x) for x in chunk_lengths[s : e + 1]))
    return {"chunk_span": span, "char_len": char_len}


def ensure_topic_chunk_ranges_ready_for_quiz(
    ranges: List[Tuple[Optional[int], Optional[int]]],
    *,
    chunk_lengths: List[int],
    min_chunks: Optional[int] = None,
    min_chars: Optional[int] = None,
    max_expand: Optional[int] = None,
) -> List[Tuple[Optional[int], Optional[int]]]:
    """Expand each (start,end) range so every topic has enough evidence for exam generation.

    Design choice: allow overlaps between topics (do NOT shrink neighbors).
    This keeps the topic list stable while guaranteeing enough context per topic.
    """
    n = len(chunk_lengths)
    if n <= 0:
        return ranges

    min_chunks_i = int(min_chunks) if min_chunks is not None else int(getattr(settings, 'TOPIC_MIN_CHUNKS_FOR_QUIZ', 4) or 4)
    min_chars_i = int(min_chars) if min_chars is not None else int(getattr(settings, 'TOPIC_MIN_CHARS_FOR_QUIZ', 1400) or 1400)
    max_expand_i = int(max_expand) if max_expand is not None else int(getattr(settings, 'TOPIC_MAX_EXPAND_CHUNKS', 6) or 6)

    out: List[Tuple[Optional[int], Optional[int]]] = []

    for (s0, e0) in (ranges or []):
        if s0 is None or e0 is None:
            out.append((s0, e0))
            continue
        try:
            s = max(0, int(s0))
            e = min(n - 1, int(e0))
        except Exception:
            out.append((s0, e0))
            continue
        if e < s:
            out.append((s, e))
            continue

        steps = 0
        while steps < max_expand_i:
            st = topic_range_stats(start_chunk_index=s, end_chunk_index=e, chunk_lengths=chunk_lengths)
            if st["chunk_span"] >= min_chunks_i and st["char_len"] >= min_chars_i:
                break
            moved = False
            # Expand both sides when possible to preserve centrality.
            if s > 0:
                s -= 1
                moved = True
            if e < (n - 1) and (topic_range_stats(start_chunk_index=s, end_chunk_index=e, chunk_lengths=chunk_lengths)["chunk_span"] < min_chunks_i
                                 or topic_range_stats(start_chunk_index=s, end_chunk_index=e, chunk_lengths=chunk_lengths)["char_len"] < min_chars_i):
                e += 1
                moved = True
            if not moved:
                break
            steps += 1

        out.append((s, e))

    return out


def build_topic_preview_for_teacher(doc_id: int, db: "Session") -> Dict[str, Any]:
    """Build a concise review payload so teachers can approve/reject extracted topics."""
    from app.models.document import Document
    from app.models.document_topic import DocumentTopic

    doc = db.query(Document).filter(Document.id == int(doc_id)).first()
    if not doc:
        raise ValueError("Document not found")

    topics = (
        db.query(DocumentTopic)
        .filter(DocumentTopic.document_id == int(doc_id))
        .order_by(DocumentTopic.topic_index.asc(), DocumentTopic.id.asc())
        .all()
    )

    topic_items: List[Dict[str, Any]] = []
    for t in topics:
        md = getattr(t, "metadata_json", {}) or {}
        coverage = float(md.get("coverage_score") or 0.0)
        confidence = str(md.get("confidence") or "").strip().lower()
        if confidence not in {"high", "medium", "low"}:
            if coverage >= 0.66:
                confidence = "high"
            elif coverage >= 0.33:
                confidence = "medium"
            else:
                confidence = "low"

        sample_excerpt = str(
            md.get("sample_excerpt")
            or md.get("sample_content")
            or getattr(t, "summary", "")
            or ""
        ).strip()
        sample_excerpt = re.sub(r"\s+", " ", sample_excerpt)[:300]

        page_start = getattr(t, "page_start", None)
        page_end = getattr(t, "page_end", None)
        if page_start and page_end:
            page_hint = f"Trang {int(page_start)}-{int(page_end)}"
        elif page_start:
            page_hint = f"Trang {int(page_start)}"
        else:
            page_hint = "Chưa xác định"

        topic_items.append(
            {
                "topic_id": int(t.id),
                "title": str(getattr(t, "teacher_edited_title", None) or t.title or ""),
                "summary": str(getattr(t, "summary", "") or "").strip(),
                "keywords": list(getattr(t, "keywords", []) or []),
                "coverage_score": max(0.0, min(1.0, coverage)),
                "confidence": confidence,
                "sample_excerpt": sample_excerpt,
                "page_hint": page_hint,
                "status": str(getattr(t, "status", "pending_review") or "pending_review"),
            }
        )

    unreviewed_count = sum(1 for item in topic_items if item.get("status") == "pending_review")
    return {
        "doc_id": int(doc.id),
        "doc_title": str(doc.title or ""),
        "topics": topic_items,
        "total_topics": len(topic_items),
        "unreviewed_count": int(unreviewed_count),
    }


def _build_topic_practice_pack(title: str, key_points: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """Build a 3-3-3 practice pack for a single topic.

    The stems are deterministic and constrained to topic signals only.
    """
    seeds = [str(x).strip() for x in (key_points or []) if str(x).strip()]
    if not seeds:
        seeds = [str(title).strip() or "nội dung chủ đề"]

    def _pick(i: int) -> str:
        return seeds[i % len(seeds)]

    easy = [
        {
            "stem": f"Khái niệm nào mô tả đúng nhất: {_pick(0)}?",
            "explanation": "Nhận diện đúng thuật ngữ cốt lõi theo nội dung vừa học.",
        },
        {
            "stem": f"Nêu ý chính của nội dung: {_pick(1)}.",
            "explanation": "Tóm tắt ngắn gọn giúp kiểm tra mức độ hiểu cơ bản.",
        },
        {
            "stem": f"Trong chủ đề '{title}', {_pick(2)} thuộc nhóm kiến thức nào?",
            "explanation": "Phân loại đúng giúp tránh nhầm lẫn giữa các phần gần nhau.",
        },
    ]
    medium = [
        {
            "stem": f"Áp dụng '{_pick(0)}' để xử lý một tình huống gần với ví dụ trong bài.",
            "explanation": "Cần nêu các bước áp dụng theo trình tự hợp lý.",
        },
        {
            "stem": f"So sánh {_pick(1)} với {_pick(2)} và chỉ ra điểm khác nhau chính.",
            "explanation": "Bài yêu cầu phân biệt khái niệm và bối cảnh sử dụng.",
        },
        {
            "stem": f"Từ '{_pick(0)}', hãy biến đổi/triển khai thành kết quả cơ bản liên quan đến chủ đề.",
            "explanation": "Kiểm tra khả năng áp dụng thay vì chỉ ghi nhớ định nghĩa.",
        },
    ]
    hard = [
        {
            "stem": f"Kết hợp {_pick(0)} và {_pick(1)} để giải quyết một bài toán nhiều bước.",
            "explanation": "Cần lập luận rõ từng bước, chỉ ra giả thiết và kết luận.",
        },
        {
            "stem": f"Phân tích sai lầm thường gặp khi vận dụng {_pick(2)} trong chủ đề '{title}'.",
            "explanation": "Bài khó vì đòi hỏi vừa hiểu bản chất vừa phát hiện lỗi tinh vi.",
        },
        {
            "stem": f"Đề xuất cách kiểm chứng kết quả khi áp dụng đồng thời {_pick(1)} và {_pick(2)}.",
            "explanation": "Đánh giá tư duy tổng hợp và khả năng tự kiểm tra tính đúng đắn.",
        },
    ]
    return {"easy": easy, "medium": medium, "hard": hard}


def generate_topic_map_from_extracted_text(
    *,
    document_title: str,
    extracted_text: str,
    toc_hints: Optional[List[str]] = None,
    page_markers: Optional[List[str]] = None,
    chunk_previews: Optional[List[str]] = None,
    max_topics: int = 24,
) -> Dict[str, Any]:
    """Generate a textbook-faithful topic map from normalized extracted text.

    Output contract:
    {"topics":[{"title","summary","keywords","outline","study_guide_md","practice_pack"}]}
    """
    text = str(extracted_text or "").strip()
    if not text:
        return {"topics": []}

    extracted = extract_topics(text, include_details=False, max_topics=int(max_topics))
    topics = extracted.get("topics") if isinstance(extracted, dict) else []
    if not isinstance(topics, list):
        topics = []

    # Optional hints are merged into text context, but never create standalone topics.
    hint_blob = "\n".join([*(toc_hints or []), *(page_markers or []), *(chunk_previews or [])]).strip()

    out_topics: List[Dict[str, Any]] = []
    for topic in topics:
        title = str(topic.get("title") or "").strip()
        if not title:
            continue
        banned = ["bài tập", "luyện tập", "câu hỏi", "đáp án", "lời giải", "quiz"]
        title_l = title.lower()
        if any(x in title_l for x in banned):
            continue

        body = str(topic.get("body") or "").strip()
        if hint_blob and body:
            body = f"{body}\n\n{hint_blob[:1200]}"
        details = build_topic_details(body, title=title)
        keywords = [str(k).strip() for k in (details.get("key_points") or topic.get("keywords") or []) if str(k).strip()][:10]
        outline = [str(x).strip() for x in (details.get("outline") or []) if str(x).strip()][:7]
        summary = " ".join([str(x).strip() for x in (details.get("key_points") or [])[:2] if str(x).strip()]).strip()
        if not summary:
            summary = str(topic.get("summary") or "").strip()
        summary = summary[:420]

        pack = _build_topic_practice_pack(title, details.get("key_points") or [])
        out_topics.append(
            {
                "title": " ".join(title.split())[:120],
                "summary": summary,
                "keywords": keywords[:10],
                "outline": outline[:7],
                "study_guide_md": str(details.get("study_guide_md") or "").strip()[:9000],
                "practice_pack": pack,
            }
        )

    # Quality gate: keep a practical number of topics, avoid empty items.
    out_topics = [t for t in out_topics if t.get("title") and t.get("summary")]
    return {"topics": out_topics[: max(12, min(60, int(max_topics)))]}
    
