from __future__ import annotations

"""Heuristic essay grading (offline fallback).

This project supports LLM-based grading for essays/homework. However, users sometimes run
the system in offline mode (no OpenAI key / no local OpenAI-compatible server).

When ESSAY_AUTO_GRADE=always (or HOMEWORK_AUTO_GRADE=always), we still want to return a
usable score + feedback so students can continue learning without waiting for a teacher.

This grader is deliberately conservative:
  - It never uses external knowledge.
  - It only looks at the student's answer, the stem, and the provided evidence chunks.
  - It scores based on coverage of key terms, structure, presence of examples, and basic clarity.

Limitations:
  - Heuristic grading cannot reliably judge deep correctness.
  - For high-stakes exams, enable an LLM grader or human grading.
"""

import re
from typing import Any, Dict, List, Tuple


_WORD_RX = re.compile(r"[A-Za-zÀ-ỹ0-9_]+", flags=re.UNICODE)


_STOPWORDS = {
    # Vietnamese (minimal but effective)
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
    "theo",
    "như",
    "vì",
    "nên",
    "có",
    "không",
    "để",
    "bằng",
    "trên",
    "dưới",
    "nhiều",
    "ít",
    "mỗi",
    "khác",
    "nhau",
    "sau",
    "trước",
    "đây",
    "đó",
    "nếu",
    "thì",
    "vẫn",
    "đang",
    "đã",
    "sẽ",
    "cần",
    "phải",
    "cũng",
    "hay",
    "rất",
    "nữa",
    "những",
    "điều",
    "cách",
    "ví",
    "dụ",
    # English
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
    "as",
    "it",
    "be",
    "by",
}


def _tokenize(text: str) -> List[str]:
    toks = [t.lower() for t in _WORD_RX.findall(text or "")]
    out: List[str] = []
    for t in toks:
        if len(t) < 3:
            continue
        if t in _STOPWORDS:
            continue
        # drop pure numbers
        if t.isdigit():
            continue
        out.append(t)
    return out


def _extract_keywords(*, evidence_texts: List[str], stem: str, top_k: int = 12) -> List[str]:
    """Pick top keywords from evidence + stem by frequency.

    We intentionally keep this simple and deterministic.
    """
    freq: Dict[str, int] = {}

    for txt in (evidence_texts or []):
        for t in _tokenize(txt):
            freq[t] = freq.get(t, 0) + 1

    # Stem terms get a small boost
    for t in _tokenize(stem or ""):
        freq[t] = freq.get(t, 0) + 2

    if not freq:
        return []

    items = sorted(freq.items(), key=lambda kv: (kv[1], len(kv[0])), reverse=True)
    kws: List[str] = []
    for w, _ in items:
        # avoid very generic leftovers
        if w in _STOPWORDS:
            continue
        kws.append(w)
        if len(kws) >= int(top_k):
            break
    return kws


def _keyword_coverage(answer_text: str, keywords: List[str]) -> Tuple[float, List[str], List[str]]:
    """Return (coverage_ratio, present, missing) for keyword set."""
    if not keywords:
        return 0.0, [], []
    ans = (answer_text or "").lower()
    present: List[str] = []
    missing: List[str] = []
    for kw in keywords:
        if re.search(rf"\b{re.escape(kw)}\b", ans, flags=re.IGNORECASE):
            present.append(kw)
        else:
            missing.append(kw)
    cov = float(len(present)) / float(max(1, len(keywords)))
    return cov, present, missing


def _structure_score(answer_text: str) -> float:
    ans = answer_text or ""
    if not ans.strip():
        return 0.0

    score = 0.0

    # list / steps
    if re.search(r"(^|\n)\s*([-*•]|\d+\s*[\.)])\s+", ans):
        score += 0.45
    if re.search(r"\b(đầu\s*tiên|trước\s*hết|tiếp\s*theo|sau\s*đó|cuối\s*cùng|bước)\b", ans, flags=re.IGNORECASE):
        score += 0.35

    # some connective words indicates reasoning
    if re.search(r"\b(vì|do\s*đó|nên|tuy\s*nhiên|mặt\s*khác|do\s*vậy)\b", ans, flags=re.IGNORECASE):
        score += 0.2

    return max(0.0, min(1.0, score))


def _example_score(answer_text: str) -> float:
    ans = answer_text or ""
    if not ans.strip():
        return 0.0

    if re.search(r"\b(ví\s*dụ|vd\b|chẳng\s*hạn|tình\s*huống|giả\s*sử|case\b|scenario)\b", ans, flags=re.IGNORECASE):
        return 1.0

    # weak signal: contains a concrete instance (numbers/dates) + >= 2 sentences
    sent = [s for s in re.split(r"[\.!?]+\s*", ans) if s.strip()]
    has_num = bool(re.search(r"\d", ans))
    if has_num and len(sent) >= 2:
        return 0.6
    return 0.0


def _clarity_score(answer_text: str) -> float:
    ans = (answer_text or "").strip()
    if not ans:
        return 0.0

    # sentence-level heuristic
    sent = [s.strip() for s in re.split(r"[\.!?]+\s*", ans) if s.strip()]
    toks = _tokenize(ans)

    if not toks:
        return 0.2

    avg_sent_len = 999.0
    if sent:
        lens = [len(_tokenize(s)) for s in sent if _tokenize(s)]
        if lens:
            avg_sent_len = float(sum(lens)) / float(len(lens))

    # repetition ratio
    freq: Dict[str, int] = {}
    for t in toks:
        freq[t] = freq.get(t, 0) + 1
    top = max(freq.values()) if freq else 1
    rep_ratio = float(top) / float(max(1, len(toks)))

    score = 1.0
    if avg_sent_len > 34:
        score -= 0.25
    elif avg_sent_len > 26:
        score -= 0.15

    if rep_ratio > 0.18:
        score -= 0.25
    elif rep_ratio > 0.12:
        score -= 0.12

    # very short answers are rarely clear
    if len(ans) < 120:
        score -= 0.2
    elif len(ans) < 220:
        score -= 0.08

    return max(0.0, min(1.0, score))


def grade_essay_heuristic(
    *,
    stem: str,
    answer_text: str,
    rubric: List[Dict[str, Any]],
    max_points: int,
    evidence_chunks: List[Dict[str, Any]] | None,
) -> Dict[str, Any]:
    """Deterministic grading.

    Returns:
      {score_points, comment, rubric_breakdown}
    """
    mp = max(1, int(max_points or 10))
    rb: List[Dict[str, Any]] = [x for x in (rubric or []) if isinstance(x, dict)]
    if not rb:
        rb = [{"criterion": "Đúng trọng tâm và có giải thích", "points": mp}]

    evidence_texts = []
    for c in (evidence_chunks or []):
        t = c.get("text") if isinstance(c, dict) else None
        if isinstance(t, str) and t.strip():
            evidence_texts.append(t)

    keywords = _extract_keywords(evidence_texts=evidence_texts, stem=stem or "", top_k=12)
    cov, present, missing = _keyword_coverage(answer_text, keywords)
    struct = _structure_score(answer_text)
    ex = _example_score(answer_text)
    clarity = _clarity_score(answer_text)

    overall = max(0.0, min(1.0, 0.45 * cov + 0.25 * struct + 0.15 * ex + 0.15 * clarity))

    def _pick_aspect(criterion: str) -> float:
        c = (criterion or "").lower()
        if any(k in c for k in ["trọng tâm", "đầy đủ", "chính xác", "đúng"]):
            return cov
        if any(k in c for k in ["lập luận", "bước", "logic", "giải thích", "quy trình"]):
            return max(struct, 0.25 * cov)
        if any(k in c for k in ["ví dụ", "áp dụng", "tình huống", "minh hoạ", "minh họa"]):
            return max(ex, 0.2 * cov)
        if any(k in c for k in ["trình bày", "mạch lạc", "rõ ràng"]):
            return clarity
        return overall

    rubric_breakdown: List[Dict[str, Any]] = []
    awarded_total = 0

    for it in rb:
        crit = str(it.get("criterion") or "").strip() or "Tiêu chí"
        try:
            pts = int(it.get("points", 0) or 0)
        except Exception:
            pts = 0
        if pts <= 0:
            continue

        aspect = _pick_aspect(crit)
        pa = int(round(float(pts) * float(aspect)))
        pa = max(0, min(int(pts), pa))
        awarded_total += pa

        note = None
        if aspect < 0.35 and any(k in crit.lower() for k in ["trọng tâm", "đầy đủ", "chính xác", "đúng"]):
            # suggest missing key terms (limit)
            miss = [m for m in missing if m not in present][:5]
            if miss:
                note = f"Thiếu các ý/thuật ngữ quan trọng: {', '.join(miss)}."
        elif aspect < 0.4 and any(k in crit.lower() for k in ["ví dụ", "áp dụng", "tình huống"]):
            note = "Chưa có ví dụ/tình huống cụ thể để minh hoạ."
        elif aspect < 0.4 and any(k in crit.lower() for k in ["lập luận", "bước", "logic", "giải thích"]):
            note = "Nên trình bày theo các bước/lập luận rõ ràng (gạch đầu dòng hoặc đánh số)."
        elif aspect < 0.4 and any(k in crit.lower() for k in ["trình bày", "mạch lạc", "rõ ràng"]):
            note = "Trình bày còn rối hoặc quá ngắn; nên viết câu ngắn hơn và tách ý."

        rubric_breakdown.append(
            {
                "criterion": crit,
                "max_points": int(pts),
                "points_awarded": int(pa),
                "comment": note,
            }
        )

    # Normalize total to mp (keep rubric max if provided)
    rb_max = sum(int(x.get("max_points", 0) or 0) for x in rubric_breakdown) or mp
    rb_max = int(max(1, rb_max))

    # If rubric sum != mp, scale to mp for consistency
    score_points = int(round(float(awarded_total) * float(mp) / float(rb_max)))
    score_points = max(0, min(mp, score_points))

    # Ensure breakdown sums to score_points (best-effort)
    if rubric_breakdown:
        # re-scale each row to mp
        scaled: List[Dict[str, Any]] = []
        for row in rubric_breakdown:
            mx = int(row.get("max_points", 0) or 0)
            pa = int(row.get("points_awarded", 0) or 0)
            new_mx = int(round(float(mx) * float(mp) / float(rb_max)))
            new_mx = max(0, new_mx)
            new_pa = int(round(float(pa) * float(mp) / float(rb_max)))
            new_pa = max(0, min(new_mx, new_pa)) if new_mx > 0 else 0
            row2 = dict(row)
            row2["max_points"] = new_mx
            row2["points_awarded"] = new_pa
            scaled.append(row2)

        # fix drift
        drift = score_points - sum(int(x.get("points_awarded", 0) or 0) for x in scaled)
        if scaled and drift != 0:
            scaled[0]["points_awarded"] = max(0, min(int(scaled[0]["max_points"]), int(scaled[0]["points_awarded"]) + drift))

        rubric_breakdown = scaled

    # Feedback (2-5 sentences)
    feedback: List[str] = []
    if len((answer_text or "").strip()) < 120:
        feedback.append("Bài làm còn khá ngắn; nên viết rõ ý theo rubric.")
    if cov < 0.45 and keywords:
        miss = [m for m in missing if m not in present][:5]
        if miss:
            feedback.append(f"Bạn nên bổ sung các ý/thuật ngữ chính: {', '.join(miss)}.")
    if struct < 0.45:
        feedback.append("Hãy trình bày theo các bước hoặc gạch đầu dòng để lập luận mạch lạc hơn.")
    if ex < 0.4:
        feedback.append("Nên thêm 1 ví dụ/tình huống cụ thể để minh hoạ và tăng điểm.")
    if clarity < 0.5:
        feedback.append("Chú ý trình bày: tách ý, viết câu ngắn hơn và dùng liên từ để nối ý.")
    if not feedback:
        feedback.append("Bài làm tương đối tốt. Để cải thiện, hãy liên hệ chặt hơn với các ý chính trong tài liệu và nêu ví dụ cụ thể.")

    # cap sentences
    comment = " ".join(feedback[:5]).strip()

    return {
        "score_points": int(score_points),
        "comment": comment,
        "rubric_breakdown": rubric_breakdown,
    }
