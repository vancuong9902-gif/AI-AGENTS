from __future__ import annotations

import random
import copy
import json
import logging
import math
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from difflib import SequenceMatcher

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import func

from fastapi import HTTPException

from app.models.attempt import Attempt
from app.models.document_chunk import DocumentChunk
from app.models.document import Document
from app.models.document_topic import DocumentTopic
from app.models.question import Question
from app.models.quiz_set import QuizSet
from app.models.classroom_assessment import ClassroomAssessment
from app.models.classroom import ClassroomMember, Classroom
from app.models.diagnostic_attempt import DiagnosticAttempt
from app.models.learner_profile import LearnerProfile
from app.services.rag_service import retrieve_and_log, auto_document_ids_for_query
from app.services.corrective_rag import corrective_retrieve_and_log
from app.services.text_quality import filter_chunks_by_quality
from app.services.user_service import ensure_user_exists
from app.core.config import settings
from app.services.llm_service import llm_available, chat_json, pack_chunks
from app.services.language_service import preferred_question_language, detect_language_heuristic
from app.services.heuristic_grader import grade_essay_heuristic
from app.services.quiz_service import (
    _generate_mcq_with_llm,
    _generate_mcq_from_chunks,
    clean_mcq_questions,
    _quiz_refine_enabled,
    _llm_refine_mcqs,
)
from app.services.bloom import infer_bloom_level, normalize_bloom_level
from app.services.embedding_service import embed_texts

# Keep topic ranges tight in DB (for clean topic display) and expand only when generating assessments.
from app.services.topic_service import ensure_topic_chunk_ranges_ready_for_quiz
from app.services.topic_service import build_topic_details
from app.services.topic_service import clean_text_for_generation


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[\.\?!\n])\s+")


_TOPIC_IN_STEM_RE = re.compile(r"'([^']+)'|\"([^\"]+)\"|“([^”]+)”")
_STEM_PUNCT_RE = re.compile(r"[^\w\sÀ-ỹ]", re.UNICODE)


def _normalize_stem_for_dedup(stem: str, *, max_len: int = 120) -> str:
    s = str(stem or "").strip().lower()
    if not s:
        return ""
    s = _STEM_PUNCT_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[: int(max_len)].strip()
_TRAILING_PUNCT_RE = re.compile(r"[\s\?\!\.,;:]+$")


def _normalize_stem_for_dedup(stem: str, *, max_chars: int = 120) -> str:
    """Normalize question stem so duplicate checks are stable across paraphrases."""
    s = " ".join(str(stem or "").strip().lower().split())
    s = _TRAILING_PUNCT_RE.sub("", s)
    if max_chars > 0:
        s = s[:max_chars]
    return s


def _is_dup(stem: str, excluded_stems: set[str] | None = None, similarity_threshold: float = 0.72) -> bool:
    """Return True when stem is too similar to any excluded stem."""
    if not excluded_stems or not stem:
        return False
    s = _normalize_stem_for_dedup(stem)
    if not s:
        return False
    return any(
        SequenceMatcher(None, s, _normalize_stem_for_dedup(ex)).ratio() >= float(similarity_threshold)
        for ex in excluded_stems
        if ex
    )


def get_used_question_stems(db: Session, *, user_id: int, kinds: list[str]) -> set[str]:
    """Load normalized stems from prior attempts of selected quiz kinds."""
    kind_list = [str(k or "").strip().lower() for k in (kinds or []) if str(k or "").strip()]
    if not kind_list:
        return set()

    rows = (
        db.query(Question.stem)
        .join(QuizSet, QuizSet.id == Question.quiz_set_id)
        .join(Attempt, Attempt.quiz_set_id == QuizSet.id)
        .filter(Attempt.user_id == int(user_id), QuizSet.kind.in_(kind_list))
        .all()
    )
    out: set[str] = set()
    for r in rows:
        raw = r[0] if isinstance(r, (tuple, list)) else r
        norm = _normalize_stem_for_dedup(str(raw or ""))
        if norm:
            out.add(norm)
    return out
_TOK_RE = re.compile(r"[\wÀ-ỹ]+", re.UNICODE)


def _token_set(text: str) -> set[str]:
    return {t for t in _TOK_RE.findall((text or "").lower()) if len(t) >= 2}


def _jaccard_similarity(a: str, b: str) -> float:
    sa, sb = _token_set(a), _token_set(b)
    if not sa or not sb:
        return 0.0
    return float(len(sa & sb)) / float(max(1, len(sa | sb)))


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    na = math.sqrt(sum(float(x) * float(x) for x in a))
    nb = math.sqrt(sum(float(y) * float(y) for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return float(dot / (na * nb))


def _cap_int(x: Any, *, default: int, lo: int, hi: int) -> int:
    try:
        n = int(x)
    except Exception:
        n = int(default)
    return max(int(lo), min(int(hi), int(n)))


def _heuristic_estimated_minutes(q: Dict[str, Any], *, level: str) -> int:
    """Fallback time estimation (minutes) when no LLM is available.

    We keep it conservative and predictable so the UI timer doesn't feel random.
    """

    qtype = (q.get("type") or "").strip().lower()
    bloom = (q.get("bloom_level") or "understand").strip().lower()
    stem = str(q.get("stem") or "")
    max_points = 0
    try:
        max_points = int(q.get("max_points") or 0)
    except Exception:
        max_points = 0

    # Base minutes by question type
    if qtype == "essay":
        base = 8
    else:
        base = 2

    # Bloom multiplier
    bloom_mult = {
        "remember": 0.8,
        "understand": 1.0,
        "apply": 1.2,
        "analyze": 1.4,
        "evaluate": 1.6,
        "create": 1.8,
    }.get(bloom, 1.0)

    # Level multiplier (beginner usually needs more time)
    lvl = (level or "beginner").strip().lower()
    lvl_mult = {"beginner": 1.2, "intermediate": 1.0, "advanced": 0.9}.get(lvl, 1.0)

    # Stem length adjustment
    L = len(stem)
    length_bonus = 0
    if L >= 550:
        length_bonus = 2
    elif L >= 320:
        length_bonus = 1
    elif L >= 180:
        length_bonus = 0

    # Essay: points adjustment (more points => more time)
    points_bonus = 0
    if qtype == "essay":
        # +1 minute per ~5 points beyond 10 (cap)
        if max_points > 10:
            points_bonus = min(4, max(0, (max_points - 10 + 4) // 5))

    est = int(round((base * bloom_mult * lvl_mult) + length_bonus + points_bonus))

    if qtype == "essay":
        return _cap_int(est, default=8, lo=6, hi=20)
    return _cap_int(est, default=2, lo=1, hi=4)


def _estimate_minutes_llm(
    *,
    questions: List[Dict[str, Any]],
    level: str,
) -> Optional[List[int]]:
    """Ask the LLM to estimate minutes per question.

    Returns a list of ints (minutes) aligned with `questions`.
    """

    if not llm_available():
        return None

    # Hard cap to avoid large/slow calls.
    if not questions or len(questions) > 60:
        return None

    # Use the dominant language of stems just to phrase the prompt.
    try:
        joined = "\n".join([str(q.get("stem") or "") for q in questions][:8])
        lang = detect_language_heuristic(joined)
    except Exception:
        lang = {"code": "vi", "name": "Vietnamese"}
    lang_name = (lang.get("name") if isinstance(lang, dict) else None) or "Vietnamese"

    packed_qs = []
    for i, q in enumerate(questions, start=1):
        stem = " ".join(str(q.get("stem") or "").split())
        # keep prompts small
        stem = stem[:260] + ("…" if len(stem) > 260 else "")
        packed_qs.append(
            {
                "i": i,
                "type": (q.get("type") or "mcq"),
                "bloom_level": q.get("bloom_level") or "understand",
                "max_points": int(q.get("max_points") or 0),
                "stem_preview": stem,
            }
        )

    system = f"""You are an experienced teacher designing a *timed* test.

Task: estimate the recommended time (in minutes) an average student needs for each question.

Output language: {lang_name} (numbers only; no explanations).

Rules:
- Return STRICT JSON only.
- You MUST return exactly N integers (N = number of questions), aligned with the given order.
- Minutes must be reasonable and stable:
  - MCQ: 1–4 minutes each
  - Essay: 6–20 minutes each
- If unsure, be conservative (a bit more time, not less).

Return format:
{{"per_question_minutes":[...],"total_minutes":<int>}}
"""

    user = {
        "level": (level or "beginner"),
        "questions": packed_qs,
        "notes": [
            "MCQ includes reading + thinking + selecting an answer.",
            "Essay includes planning + writing; assume short essay for 10 points.",
        ],
    }

    try:
        data = chat_json(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.0,
            max_tokens=500,
        )
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    arr = data.get("per_question_minutes")
    if isinstance(arr, dict):
        # some models return {"1":2,...}
        try:
            arr = [arr.get(str(i)) for i in range(1, len(questions) + 1)]
        except Exception:
            arr = None
    if not isinstance(arr, list) or len(arr) != len(questions):
        return None

    out: List[int] = []
    for q, v in zip(questions, arr):
        qtype = (q.get("type") or "mcq").strip().lower()
        if qtype == "essay":
            out.append(_cap_int(v, default=_heuristic_estimated_minutes(q, level=level), lo=6, hi=20))
        else:
            out.append(_cap_int(v, default=_heuristic_estimated_minutes(q, level=level), lo=1, hi=4))
    return out


def _infer_topic_from_stem(stem: str, fallback: str = "tài liệu") -> str:
    """Infer topic for mastery tracking.

    Priority:
    1) Explicit marker like [topic: ...] or 'chủ đề: ...'
    2) Quoted keyword in stem (e.g., 'List')
    3) Heuristic keyword buckets (loops/functions/OOP/numpy/SQL/RAG)
    4) Fallback
    """
    s_raw = _normalize_ws(stem)
    s = s_raw.lower()

    # 1) explicit marker
    m = re.search(r"(?:\[\s*(?:topic|chủ đề)\s*[:=]\s*([^\]]+)\]|(?:topic|chủ đề)\s*[:=]\s*([\w\s\-/]{3,60}))", s, re.I)
    if m:
        val = next((g for g in m.groups() if g), None) or fallback
        return _normalize_ws(val).lower() or (fallback or "tài liệu").strip().lower()

    # 2) quoted keyword
    m2 = _TOPIC_IN_STEM_RE.search(s_raw)
    if m2:
        token = next((g for g in m2.groups() if g), None) or ""
        token_n = _normalize_ws(token).lower()
        if token_n in {"list", "tuple", "dict", "dictionary", "set"}:
            return "list/tuple/dict"
        if token_n in {"for", "while"}:
            return "vòng lặp"
        if token_n:
            return token_n

    # 3) heuristic buckets
    buckets = [
        ("numpy cơ bản", ["numpy", "ndarray", "np.", "broadcast", "vector", "matrix"]),
        ("sql", ["sql", "select", "where", "join", "group by", "insert", "update"]),
        ("rag", ["rag", "embedding", "vector", "faiss", "chunk", "retrieval"]),
        ("oop cơ bản", ["class", "object", "self", "__init__", "kế thừa", "inherit"]),
        ("hàm", ["def ", "return", "lambda", "tham số", "parameter", "hàm"]),
        ("vòng lặp", [" vòng lặp", "for ", "while ", "break", "continue", "range("]),
        ("list/tuple/dict", ["list", "tuple", "dict", "dictionary", "set", "index", "slice"]),
    ]
    for topic, kws in buckets:
        if any(kw in s for kw in kws):
            return topic

    # 4) fallback
    fb = (fallback or "tài liệu").strip().lower()
    # normalize overly generic fallback
    if fb in {"python cơ bản", "python co ban", "tài liệu"}:
        return "tài liệu"
    return fb or "tài liệu"


def _is_assessment_kind(kind: str) -> bool:
    # Legacy note: previously had kind="assessment" (treated as "midterm")
    return (kind or "").strip().lower() in ("midterm", "diagnostic_pre", "diagnostic_post", "assessment", "entry_test", "final_exam", "final")


def _normalize_assessment_kind(kind: str | None) -> str:
    k = (kind or "").strip().lower()
    if k == "assessment":
        return "midterm"
    if k in ("midterm", "diagnostic_pre", "diagnostic_post", "entry_test", "final_exam"):
        return k
    if k in ("final_exam", "final"):
        return "final_exam"
    # Default: treat unknown as "midterm" (in-course)
    return "midterm"


def _level_from_total(total_percent: int, *, essay_percent: int | None = None, gate_essay: bool = True) -> str:
    if total_percent < 40:
        lvl = "beginner"
    elif total_percent <= 70:
        lvl = "intermediate"
    else:
        lvl = "advanced"

    # "Cửa kiểm" essay: nếu essay quá thấp thì không lên Advanced
    if gate_essay and lvl == "advanced" and essay_percent is not None and int(essay_percent) < 30:
        return "intermediate"
    return lvl


def _split_scores_from_breakdown(breakdown: list[dict]) -> dict:
    """Return mcq_percent, essay_percent, total_percent (70/30) and point details."""
    mcq_earned = mcq_total = 0
    essay_earned = essay_total = 0
    pending = False

    for it in breakdown or []:
        t = (it.get("type") or "").lower()
        mp = int(it.get("max_points", 1) or 1)
        sp = int(it.get("score_points", 0) or 0)
        if t == "mcq":
            mcq_total += mp
            mcq_earned += sp
        elif t == "essay":
            # If there is an essay question but not graded yet, flag pending.
            if it.get("graded") is False or it.get("graded") is None:
                pending = True
                continue
            essay_total += mp
            essay_earned += sp

    mcq_percent = int(round((mcq_earned / mcq_total) * 100)) if mcq_total else 0
    essay_percent = int(round((essay_earned / essay_total) * 100)) if essay_total else 0

    total_percent = int(round(0.7 * mcq_percent + 0.3 * essay_percent))

    return {
        "mcq_percent": mcq_percent,
        "essay_percent": essay_percent,
        "total_percent": total_percent,
        "pending": bool(pending),
        "mcq_earned": mcq_earned,
        "mcq_total": mcq_total,
        "essay_earned": essay_earned,
        "essay_total": essay_total,
    }


def _topic_mastery_from_breakdown(breakdown: list[dict]) -> dict:
    """Compute mastery_by_topic (0..1) using score_points/max_points across questions."""
    earned: dict[str, int] = {}
    total: dict[str, int] = {}

    for it in breakdown or []:
        topic = (it.get("topic") or "").strip().lower() or "tài liệu"
        mp = int(it.get("max_points", 1) or 1)
        sp = int(it.get("score_points", 0) or 0)
        total[topic] = total.get(topic, 0) + mp
        earned[topic] = earned.get(topic, 0) + sp

    out: dict[str, float] = {}
    for t, tp in total.items():
        out[t] = round((earned.get(t, 0) / tp), 4) if tp else 0.0
    return out


def _difficulty_from_bloom(bloom_level: str | None) -> str:
    bloom = normalize_bloom_level(bloom_level)
    if bloom in {"remember", "understand"}:
        return "easy"
    if bloom in {"apply", "analyze"}:
        return "medium"
    return "hard"


def _build_answer_review(*, breakdown: list[dict], questions: list[Question], default_topic: str) -> list[dict[str, Any]]:
    q_map: dict[int, Question] = {int(q.id): q for q in (questions or [])}
    answer_review: list[dict[str, Any]] = []

    for item in breakdown or []:
        qid = int(item.get("question_id") or 0)
        q = q_map.get(qid)
        q_type = str(item.get("type") or getattr(q, "type", "")).strip().lower()
        topic = str(item.get("topic") or _infer_topic_from_stem(getattr(q, "stem", ""), fallback=default_topic))
        difficulty = _difficulty_from_bloom(getattr(q, "bloom_level", None))

        if q_type == "mcq":
            answer_review.append(
                {
                    "question_id": qid,
                    "stem": str(getattr(q, "stem", "") or ""),
                    "your_answer_index": int(item.get("chosen", -1) or -1),
                    "correct_answer_index": int(item.get("correct", getattr(q, "correct_index", 0)) or 0),
                    "is_correct": bool(item.get("is_correct")),
                    "explanation": str(item.get("explanation") or getattr(q, "explanation", "") or ""),
                    "topic": topic,
                    "difficulty": difficulty,
                }
            )
            continue

        max_points = int(item.get("max_points") or getattr(q, "max_points", 10) or 10)
        score_points = int(item.get("score_points") or 0)
        graded = bool(item.get("graded"))

        answer_review.append(
            {
                "question_id": qid,
                "stem": str(getattr(q, "stem", "") or ""),
                "your_answer_index": None,
                "correct_answer_index": None,
                "your_answer": str(item.get("answer_text") or ""),
                # Current data model has no `sample_answer`; reuse explanation as expected answer guidance.
                "correct_answer": str(getattr(q, "explanation", "") or ""),
                "is_correct": bool(graded and max_points > 0 and score_points >= (0.6 * max_points)),
                "explanation": str(item.get("comment") or item.get("explanation") or getattr(q, "explanation", "") or ""),
                "topic": topic,
                "difficulty": difficulty,
            }
        )

    return answer_review



def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _pick_sentences(text: str, *, min_len: int = 25, max_len: int = 160) -> List[str]:
    t = _normalize_ws(text)
    if not t:
        return []

    parts = _SENTENCE_SPLIT_RE.split(t)
    out: List[str] = []
    seen = set()
    for p in parts:
        p = _normalize_ws(p)
        if len(p) < min_len or len(p) > max_len:
            continue
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def _truncate(s: str, n: int = 160) -> str:
    s = _normalize_ws(s)
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"

_GENERIC_TOKENS = {"tài", "liệu", "co", "ban", "bản", "basic", "basics"}


def _rag_query_for_topic(topic: str, level: str) -> str:
    t = _normalize_ws(topic)
    lvl = (level or "begininer").strip().lower()
    if not t or t.lower() in {"tài liệu", "tổng hợp", "tong hop"}:
        return "tổng hợp kiến thức trọng tâm: khái niệm, ví dụ, ứng dụng, lưu ý"
    if lvl == "advanced":
        return f"{t} tình huống, so sánh, lỗi thường gặp, ứng dụng"
    if lvl == "intermediate":
        return f"{t} giải thích, so sánh, ví dụ"
    return f"{t} khái niệm, ví dụ, ghi nhớ"


def _topic_token_hits(topic: str, text: str) -> int:
    t = (topic or "").lower()
    toks = [tok for tok in re.findall(r"[\w]+", t) if tok and tok not in _GENERIC_TOKENS and len(tok) >= 3]
    if not toks:
        return 0
    body = (text or "").lower()
    return sum(1 for tok in set(toks) if tok in body)


def _pick_source_for_topic(db: Session, *, topic: str, level: str, document_ids: List[int]) -> Dict[str, Any] | None:
    """Retrieve a single best chunk as a *reference* for this topic (avoid random generic chunks)."""
    query = _rag_query_for_topic(topic, level)
    try:
        res = corrective_retrieve_and_log(
            db=db,
            query=query,
            top_k=12,
            filters={"document_ids": document_ids} if document_ids else None,
            topic=topic,
        )
        chunks = res.get("chunks") or []
        good, _bad = filter_chunks_by_quality(chunks, min_score=float(settings.OCR_MIN_QUALITY_SCORE))
        chunks = good or chunks
    except Exception:
        chunks = []

    best = None
    best_key = (-1, -1.0)
    for c in chunks:
        txt = c.get("text") or ""
        hits = _topic_token_hits(topic, txt)
        try:
            base = float(c.get("score", 0.0) or 0.0)
        except Exception:
            base = 0.0
        key = (hits, base)
        if key > best_key:
            best_key = key
            best = c

    if not best:
        return None

    best_txt = clean_text_for_generation(best.get("text") or "")
    best_txt = best_txt or (best.get("text") or "")

    return {
        "chunk_id": int(best.get("chunk_id")),
        "document_id": int(best.get("document_id")) if best.get("document_id") is not None else None,
        "document_title": best.get("document_title") or best.get("title"),
        "score": float(best.get("score", 0.0) or 0.0),
        "preview": _truncate(best_txt, 160),
        # Include a longer snippet for offline dynamic question generation.
        "text": _truncate(best_txt, 1200),
    }



def _build_mcq_question(
    *,
    topic: str,
    correct_sentence: str,
    distractors: List[str],
    source: Dict[str, Any],
) -> Dict[str, Any]:
    options = [correct_sentence] + distractors
    random.shuffle(options)
    correct_index = options.index(correct_sentence)

    # Match output language with the source/topic when offline.
    lang = detect_language_heuristic(f"{topic} {correct_sentence} {' '.join(distractors or [])}")
    lang_code = (lang.get("code") if isinstance(lang, dict) else getattr(lang, "code", None)) or "vi"
    if lang_code == "vi":
        stem = f"Chọn phát biểu ĐÚNG nhất về '{topic}'."
    else:
        stem = f"Choose the MOST correct statement about '{topic}'."

    return {
        "type": "mcq",
        "bloom_level": infer_bloom_level(stem, default="understand"),
        "stem": stem,
        "options": [_truncate(o, 140) for o in options],
        "correct_index": int(correct_index),
        "explanation": _truncate(correct_sentence, 220),
        "sources": [source],
        "max_points": 1,
        "rubric": [],
    }


def _build_essay_question(*, topic: str, level: str, source: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Create an essay question that adapts to the topic's *actual* content.

    Requirement: avoid a fixed/preset question framework.
    Heuristic (offline) generator uses a small topic profile mined from the best chunk.
    """

    t = _normalize_ws(topic) or "tài liệu"
    lvl = (level or "beginner").strip().lower()

    # Use richer snippet when available.
    src_text = ""
    if isinstance(source, dict):
        src_text = str(source.get("text") or source.get("preview") or "")

    # Best-effort language match for OFFLINE generation.
    lang = detect_language_heuristic(f"{t}\n{src_text}")
    lang_code = (lang.get("code") if isinstance(lang, dict) else getattr(lang, "code", None)) or "vi"
    is_vi = (lang_code == "vi")

    profile = build_topic_details(src_text, title=t) if src_text.strip() else {
        "title": t,
        "outline": [],
        "key_points": [],
        "definitions": [],
        "examples": [],
        "formulas": [],
        "faq": [],
        "misconceptions": [],
        "exercises": [],
    }

    defs = profile.get("definitions") or []
    kps = profile.get("key_points") or []
    outl = profile.get("outline") or []
    exs = profile.get("examples") or []
    forms = profile.get("formulas") or []
    misc = profile.get("misconceptions") or []

    # Candidate stems (choose based on what exists, not a fixed order).
    cands: List[Dict[str, Any]] = []

    def _add(stem: str, bloom: str):
        s = _ensure_topic_in_essay_stem(_normalize_ws(stem), t)
        if len(s) < 30:
            return
        cands.append({"stem": s, "bloom": bloom})

    if isinstance(forms, list) and forms:
        _add(
            (
                f"Giải thích công thức/quy tắc liên quan đến '{t}' (ý nghĩa của các thành phần, điều kiện áp dụng). "
                "Sau đó, đặt một ví dụ số/liên hệ thực tế và trình bày cách bạn áp dụng từng bước để ra kết quả."
                if is_vi
                else f"Explain a formula/rule related to '{t}' (meaning of its parts and when it applies). "
                "Then give a small practical example and show how you apply it step by step to reach the result."
            ),
            "apply" if lvl == "beginner" else "analyze",
        )

    if isinstance(outl, list) and outl:
        _add(
            (
                f"Trình bày quy trình/các bước cốt lõi của '{t}'. "
                "Với mỗi bước, nêu mục tiêu và một lỗi/nhầm lẫn dễ mắc phải."
                if is_vi
                else f"Describe the core process/steps of '{t}'. "
                "For each step, state its goal and one common mistake or misconception."
            ),
            "analyze" if lvl != "advanced" else "evaluate",
        )

    if isinstance(kps, list) and kps:
        _add(
            (
                f"Chọn 3 ý chính quan trọng nhất trong '{t}' và giải thích mối liên hệ giữa chúng. "
                "Kết luận: nếu bỏ qua một ý, hệ quả có thể là gì?"
                if is_vi
                else f"Pick 3 key ideas in '{t}' and explain how they relate. "
                "Conclude: what could happen if one idea is ignored?"
            ),
            "analyze" if lvl != "beginner" else "understand",
        )

    if isinstance(misc, list) and misc:
        _add(
            (
                f"Nêu một sai lầm/hiểu lầm phổ biến về '{t}' và cách phát hiện. "
                "Hãy đề xuất một checklist ngắn để tránh lỗi này trong thực tế."
                if is_vi
                else f"Describe a common mistake/misconception about '{t}' and how to spot it. "
                "Propose a short checklist to avoid this error in practice."
            ),
            "evaluate" if lvl != "beginner" else "apply",
        )

    if isinstance(exs, list) and exs:
        _add(
            (
                f"Phân tích một ví dụ/tình huống thực tiễn liên quan '{t}': bối cảnh, các quyết định chính, và kết quả. "
                "Nếu thay đổi một điều kiện, bạn dự đoán kết quả thay đổi ra sao?"
                if is_vi
                else f"Analyze a practical scenario related to '{t}': context, key decisions, and outcomes. "
                "If one condition changes, how would you expect the outcome to change?"
            ),
            "analyze" if lvl != "beginner" else "apply",
        )

    if isinstance(defs, list) and defs:
        d0 = defs[0]
        term = (d0.get("term") if isinstance(d0, dict) else None) or t
        _add(
            (
                f"Giải thích '{term}' bằng lời của bạn và nêu 1 ví dụ minh hoạ. "
                "Sau đó, chỉ ra 1 trường hợp dễ hiểu nhầm và cách phân biệt."
                if is_vi
                else f"Explain '{term}' in your own words and give one illustrative example. "
                "Then point out one common confusion case and how to distinguish it."
            ),
            "understand" if lvl == "beginner" else "analyze",
        )

    # Generic fallback if profile is thin.
    if not cands:
        _add(
            (
                f"Đặt một bài toán thực tế cần áp dụng '{t}'. "
                "Hãy phân tích yêu cầu, đề xuất cách làm (có thể kèm pseudo-code/code ngắn) và nêu tiêu chí đánh giá kết quả."
                if is_vi
                else f"Create a real-world problem that requires applying '{t}'. "
                "Analyze the requirements, propose an approach (optionally with short pseudo-code), and state criteria to evaluate the result."
            ),
            "create" if lvl == "advanced" else "analyze",
        )

    # Pick 1 candidate: beginner -> simpler; advanced -> higher bloom.
    if lvl == "beginner":
        preferred = [c for c in cands if c["bloom"] in {"understand", "apply"}] or cands
    elif lvl == "intermediate":
        preferred = [c for c in cands if c["bloom"] in {"apply", "analyze", "evaluate"}] or cands
    else:
        preferred = [c for c in cands if c["bloom"] in {"analyze", "evaluate", "create"}] or cands

    picked = random.choice(preferred)
    stem = picked["stem"]
    bloom = picked["bloom"]

    rubric = (
        [
            {"criterion": "Đúng trọng tâm / đầy đủ ý chính", "points": 4},
            {"criterion": "Lập luận & các bước rõ ràng", "points": 3},
            {"criterion": "Ví dụ / áp dụng tình huống", "points": 2},
            {"criterion": "Trình bày rõ ràng", "points": 1},
        ]
        if is_vi
        else [
            {"criterion": "Accurate and complete key ideas", "points": 4},
            {"criterion": "Clear reasoning and steps", "points": 3},
            {"criterion": "Example / practical application", "points": 2},
            {"criterion": "Clear presentation", "points": 1},
        ]
    )

    sources = [source] if isinstance(source, dict) else []

    return {
        "type": "essay",
        "bloom_level": normalize_bloom_level(bloom),
        "stem": stem,
        "options": [],
        "correct_index": -1,
        "explanation": "Bài tự luận cần chấm theo rubric." if is_vi else "This essay question is graded using the rubric.",
        "sources": sources,
        "max_points": 10,
        "rubric": rubric,
    }


def _ensure_topic_in_essay_stem(stem: str, topic: str) -> str:
    s = (stem or '').strip()
    t = (topic or 'tài liệu').strip() or 'tài liệu'
    # Keep output language aligned with topic.
    lang = detect_language_heuristic(t)
    lang_code = (lang.get("code") if isinstance(lang, dict) else getattr(lang, "code", None)) or "vi"
    prefix = "Chủ đề" if lang_code == "vi" else "Topic"
    if not s:
        return f"{prefix} '{t}': (essay question)" if lang_code != "vi" else f"{prefix} '{t}': (câu hỏi tự luận)"

    # If the stem already starts with the *other* language's prefix, normalize it.
    sl = s.lower()
    if sl.startswith("chủ đề") and prefix != "Chủ đề":
        # Replace only the leading token, keep the rest intact.
        s = re.sub(r"(?i)^chủ\s*đề", prefix, s, count=1).strip()
        sl = s.lower()
    if sl.startswith("topic") and prefix != "Topic":
        s = re.sub(r"(?i)^topic", prefix, s, count=1).strip()
        sl = s.lower()

    if f"'{t}'" in s or f'"{t}"' in s or f"“{t}”" in s:
        return s
    if sl.startswith('chủ đề') or sl.startswith('topic'):
        return f"{prefix} '{t}': {s}"
    return f"{prefix} '{t}': {s}"


def _sanitize_rubric(rubric: Any, *, max_points: int = 10) -> List[Dict[str, Any]]:
    """Rubric must be a list of {criterion, points}. Fix common LLM issues."""
    out: List[Dict[str, Any]] = []
    if isinstance(rubric, dict):
        rubric = [rubric]
    if isinstance(rubric, list):
        for it in rubric:
            if not isinstance(it, dict):
                continue
            crit = (it.get('criterion') or '').strip()
            if not crit:
                continue
            try:
                pts = int(it.get('points', 0) or 0)
            except Exception:
                pts = 0
            if pts <= 0:
                continue
            out.append({'criterion': crit, 'points': pts})

    if not out:
        out = [
            {'criterion': 'Đúng trọng tâm / đầy đủ ý chính', 'points': 4},
            {'criterion': 'Lập luận & các bước rõ ràng', 'points': 3},
            {'criterion': 'Ví dụ / áp dụng tình huống', 'points': 2},
            {'criterion': 'Trình bày rõ ràng', 'points': 1},
        ]

    # Normalize total points to max_points
    total = sum(int(x.get('points', 0) or 0) for x in out)
    if total != int(max_points) and total > 0:
        # Scale proportionally but keep integers and at least 1
        scaled: List[int] = []
        for it in out:
            scaled.append(max(1, round(int(it['points']) * int(max_points) / total)))
        # Fix rounding drift
        drift = int(max_points) - sum(scaled)
        if drift != 0:
            scaled[0] = max(1, scaled[0] + drift)
        for it, pts in zip(out, scaled):
            it['points'] = int(pts)

    return out

def _essay_refine_enabled(*, questions: Optional[List[Dict[str, Any]]] = None, gen_mode: Optional[str] = None) -> bool:
    """Whether to run the essay "editor pass" to make prompts/rubrics more teacher-like."""
    mode = (settings.ESSAY_LLM_REFINE or "off").strip().lower()
    if mode in {"0", "false", "no"}:
        mode = "off"
    if mode == "off":
        return False
    if not llm_available():
        return False
    if mode == "always":
        return True

    # auto mode: refine when generated offline or when drafts look weak/noisy
    gm = (gen_mode or settings.QUIZ_GEN_MODE or "auto").strip().lower()
    if gm == "offline":
        return True
    qs = questions or []
    if not qs:
        return False

    # Heuristics: short stems, missing/weak rubric, missing explanations, duplicated stems
    stems = [" ".join(str(q.get("stem") or "").split()).lower() for q in qs]
    dup = len(stems) != len(set(stems))
    weak = False
    for q in qs:
        stem = " ".join(str(q.get("stem") or "").split())
        expl = " ".join(str(q.get("explanation") or "").split())
        rubric = q.get("rubric") or []
        if len(stem) < 35:
            weak = True
            break
        if len(expl) < 30:
            weak = True
            break
        if not isinstance(rubric, list) or len(rubric) < 2:
            weak = True
            break
    return bool(weak or dup)


def _llm_refine_essays(*, topic: str, level: str, chunks: List[Dict[str, Any]], questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """LLM editor pass for essay questions (rewrite stems/rubrics/explanations) grounded to evidence chunks."""
    if not questions:
        return []

    packed = pack_chunks(chunks, max_chunks=10)
    if not packed:
        return questions

    lang = preferred_question_language(packed)

    valid_ids = [int(c["chunk_id"]) for c in packed]

    def _tok(s: str) -> set[str]:
        return {w for w in re.findall(r"[\wÀ-ỹ]+", (s or "").lower()) if len(w) >= 3}

    def _best_sources(text_hint: str, k: int = 2) -> List[Dict[str, int]]:
        hint = _tok(text_hint)
        scored = []
        for c in packed:
            cid = int(c.get("chunk_id"))
            ct = _tok(f"{c.get('title') or ''} {c.get('text') or ''}")
            score = len(hint & ct)
            scored.append((score, cid))
        scored.sort(reverse=True)
        picked = [cid for score, cid in scored if score > 0][:k]
        if not picked:
            picked = [valid_ids[0]]
        return [{"chunk_id": int(x)} for x in picked]

    system = f"""Bạn là GIẢNG VIÊN RA ĐỀ (editor pass).
Nhiệm vụ: CHỈNH SỬA các câu hỏi tự luận (stem + rubric + explanation) để giống đề thi giáo viên/SGK hơn.
BẮT BUỘC bám sát ngữ liệu evidence_chunks; KHÔNG dùng kiến thức ngoài.

NGÔN NGỮ ĐẦU RA: {lang.get('name','Vietnamese')}.
- Tất cả stem/explanation/rubric phải dùng đúng ngôn ngữ này.
- Không trộn ngôn ngữ (trừ thuật ngữ chuyên ngành bắt buộc).

QUY TẮC:
- Giữ nguyên SỐ LƯỢNG câu hỏi.
- Câu hỏi PHẢI ĐỘC LẬP (standalone): học sinh không cần đọc tài liệu gốc vẫn làm được.
- Không tham chiếu 'theo tài liệu/đoạn/chương/trang/hình/bảng'.
- Không copy nguyên văn đoạn văn; diễn đạt lại rõ ràng, sư phạm.
- Mỗi câu: stem 2–4 câu, có yêu cầu rõ ràng (giải thích/so sánh/tình huống/vận dụng).
- rubric là danh sách {criterion, points}, tổng points = max_points.
- sources: mảng chunk_id (1–2) lấy từ evidence_chunks.
- bloom_level ∈ {remember,understand,apply,analyze,evaluate,create}. Với tự luận ưu tiên apply/analyze/evaluate/create theo level.

ĐẦU RA: JSON hợp lệ.
Nếu OK: {"status":"OK","questions":[...]}.
Nếu CONTEXT lỗi/thiếu: {"status":"NEED_CLEAN_TEXT","reason":"...","suggestion":"..."}.
"""

    user = {
        "topic": (topic or "bài kiểm tra").strip(),
        "level": (level or "intermediate").strip(),
        "language": lang,
        "evidence_chunks": packed,
        "draft_questions": [
            {
                "bloom_level": q.get("bloom_level"),
                "stem": q.get("stem"),
                "max_points": int(q.get("max_points", 10) or 10),
                "rubric": q.get("rubric") or [],
                "sources": q.get("sources") or [],
                "explanation": q.get("explanation") or "",
            }
            for q in (questions or [])[: int(getattr(settings, "ESSAY_LLM_REFINE_MAX_QUESTIONS", 10) or 10)]
        ],
        "constraints": [
            "Giữ nguyên max_points của từng câu.",
            "Câu hỏi phải độc lập (standalone); không tham chiếu 'tài liệu/đoạn/chương/trang/hình/bảng'.",
            "Không trích nguyên văn quá 8 từ liên tiếp từ evidence_chunks; phải diễn đạt lại.",
            "Không bịa kiến thức; nếu evidence không đủ thì trả NEED_CLEAN_TEXT.",
            "Đảm bảo rubic có ít nhất 3 tiêu chí và tổng điểm đúng max_points.",
            "Explanation 2–4 câu: gợi ý cách làm/ý chính, KHÔNG phải bài mẫu dài.",
        ],
        "output_format": {
            "questions": [
                {
                    "bloom_level": "analyze",
                    "stem": "string",
                    "explanation": "string",
                    "max_points": 10,
                    "rubric": [{"criterion": "...", "points": 4}],
                    "sources": [{"chunk_id": 123}],
                }
            ]
        },
    }

    data = chat_json(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
        temperature=0.25,
        max_tokens=2400,
    )

    if isinstance(data, dict) and str(data.get("status", "")).upper() == "NEED_CLEAN_TEXT":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "NEED_CLEAN_TEXT",
                "message": "CONTEXT không đủ rõ để chỉnh sửa (refine) câu hỏi tự luận bám tài liệu.",
                "reason": data.get("reason") or "CONTEXT thiếu/không rõ.",
                "suggestion": data.get("suggestion") or "Hãy upload file .docx hoặc PDF có text layer / hoặc copy text mục cần ra đề.",
            },
        )

    raw = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return questions

    out: List[Dict[str, Any]] = []
    max_n = min(len(questions), len(raw))
    for i in range(max_n):
        base = questions[i] if i < len(questions) else {}
        q = raw[i] if isinstance(raw[i], dict) else {}

        stem0 = " ".join(str(q.get("stem") or base.get("stem") or "").split()).strip()
        stem = _ensure_topic_in_essay_stem(stem0, topic)

        max_points = int(base.get("max_points", 10) or 10)
        rubric = _sanitize_rubric(q.get("rubric") or base.get("rubric"), max_points=max_points)

        explanation = " ".join(str(q.get("explanation") or base.get("explanation") or "").split()).strip()
        if not explanation:
            explanation = "Bài tự luận cần chấm theo rubric."

        sources = q.get("sources") if isinstance(q, dict) else None
        if isinstance(sources, dict):
            sources = [sources]
        s_ok: List[Dict[str, int]] = []
        if isinstance(sources, list):
            for it in sources:
                cid = it.get("chunk_id") if isinstance(it, dict) else it
                try:
                    cid_i = int(cid)
                except Exception:
                    continue
                if cid_i in valid_ids:
                    s_ok.append({"chunk_id": cid_i})
        s_ok = s_ok[:2]
        if not s_ok:
            s_ok = _best_sources(f"{stem} {explanation}")

        raw_bloom = q.get("bloom_level") if isinstance(q, dict) else None
        if isinstance(raw_bloom, str) and raw_bloom.strip():
            bloom = normalize_bloom_level(raw_bloom)
        else:
            bloom = normalize_bloom_level(base.get("bloom_level")) if isinstance(base, dict) else "analyze"
            bloom = bloom or infer_bloom_level(f"{stem} {explanation}", default="analyze")

        out.append(
            {
                "type": "essay",
                "bloom_level": bloom,
                "stem": stem,
                "options": [],
                "correct_index": -1,
                "explanation": explanation,
                "sources": s_ok,
                "max_points": max_points,
                "rubric": rubric,
            }
        )

    # If LLM returned fewer items, keep remaining originals
    if len(out) < len(questions):
        out.extend(questions[len(out):])

    return out


def _essay_autograde_enabled() -> bool:
    """Whether we should auto-grade essay answers.

    Modes (ENV: ESSAY_AUTO_GRADE):
      - off: never
      - auto: only when llm_available() is True
      - always: always grade. If LLM is not available, use a deterministic heuristic grader.
    """
    mode = (settings.ESSAY_AUTO_GRADE or "off").strip().lower()
    if mode in {"0", "false", "no"}:
        mode = "off"
    if mode == "off":
        return False
    if mode == "auto":
        return bool(llm_available())
    # always (or any other truthy value) -> try grading even offline
    return True


def _auto_grade_essays_for_attempt(db: Session, *, quiz_set: QuizSet, attempt: Attempt) -> Optional[Dict[str, Any]]:
    """Auto-grade essay answers inside attempt.breakdown_json.

    - If llm_available(): use the LLM rubric grader (best quality).
    - Else: use a deterministic heuristic grader when ESSAY_AUTO_GRADE=always.
    """
    bd = copy.deepcopy(attempt.breakdown_json or [])
    if not bd:
        return None

    # Build question map for rubric/stem/sources
    questions = (
        db.query(Question)
        .filter(Question.quiz_set_id == int(quiz_set.id))
        .order_by(Question.order_no.asc())
        .all()
    )
    qmap = {int(q.id): q for q in questions}

    min_chars = int(getattr(settings, "ESSAY_AUTO_GRADE_MIN_CHARS", 40) or 40)
    max_grade = int(getattr(settings, "ESSAY_LLM_REFINE_MAX_QUESTIONS", 10) or 10)  # reuse as a safe cap
    graded_count = 0

    use_llm = bool(llm_available())

    def _fetch_chunks_for_sources(srcs: Any) -> List[Dict[str, Any]]:
        if isinstance(srcs, dict):
            srcs = [srcs]
        ids: List[int] = []
        if isinstance(srcs, list):
            for it in srcs:
                cid = it.get("chunk_id") if isinstance(it, dict) else it
                try:
                    ids.append(int(cid))
                except Exception:
                    continue
        ids = list(dict.fromkeys(ids))[:6]
        if not ids:
            return []
        rows = db.query(DocumentChunk).filter(DocumentChunk.id.in_(ids)).all()
        # optional titles
        dids = list({int(r.document_id) for r in rows if getattr(r, "document_id", None) is not None})
        dmap: Dict[int, str] = {}
        if dids:
            docs = db.query(Document).filter(Document.id.in_(dids)).all()
            dmap = {int(d.id): (d.title or str(d.id)) for d in docs}
        outc = []
        for r in rows:
            outc.append({
                "chunk_id": int(r.id),
                "document_id": int(r.document_id) if getattr(r, "document_id", None) is not None else None,
                "document_title": dmap.get(int(r.document_id)) if getattr(r, "document_id", None) is not None else None,
                "text": r.text,
            })
        return outc

    def _grade_with_llm(*, stem: str, rubric: List[Dict[str, Any]], max_points: int, answer_text: str, evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
        packed = pack_chunks(evidence, max_chunks=8)
        system = """Bạn là GIẢNG VIÊN CHẤM TỰ LUẬN.
Chỉ dựa trên: (1) câu hỏi, (2) bài làm học sinh, (3) rubric, (4) evidence_chunks.
KHÔNG dùng kiến thức ngoài evidence_chunks.

Yêu cầu:
- Chấm điểm chặt, công bằng, đúng rubric.
- Nếu bài trả lời sai trọng tâm hoặc bịa ngoài evidence => trừ điểm mạnh.
- Trả về JSON hợp lệ, không thêm chữ ngoài JSON.

ĐẦU RA:
{
  "score_points": <int 0..max_points>,
  "comment": "feedback ngắn 2-5 câu, sư phạm",
  "rubric_breakdown": [
    {"criterion":"...","max_points":<int>,"points_awarded":<int>,"comment":"..."}
  ]
}
"""
        user = {
            "question": {"stem": stem, "max_points": int(max_points), "rubric": rubric},
            "answer_text": answer_text,
            "evidence_chunks": packed,
        }
        data = chat_json(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.0,
            max_tokens=1200,
        )
        if not isinstance(data, dict):
            return {"score_points": 0, "comment": "Không chấm được (đầu ra không hợp lệ).", "rubric_breakdown": []}

        try:
            sp = int(data.get("score_points", 0) or 0)
        except Exception:
            sp = 0
        sp = max(0, min(int(max_points), sp))

        rb = data.get("rubric_breakdown")
        if isinstance(rb, dict):
            rb = [rb]
        out_rb: List[Dict[str, Any]] = []
        if isinstance(rb, list):
            for it in rb:
                if not isinstance(it, dict):
                    continue
                crit = (it.get("criterion") or "").strip()
                if not crit:
                    continue
                try:
                    mp = int(it.get("max_points", 0) or 0)
                except Exception:
                    mp = 0
                try:
                    pa = int(it.get("points_awarded", 0) or 0)
                except Exception:
                    pa = 0
                if mp <= 0:
                    # fallback: infer from rubric
                    mp = next((int(x.get("points", 0) or 0) for x in rubric if (x.get("criterion") or "").strip() == crit), 0)
                if mp <= 0:
                    continue
                pa = max(0, min(mp, pa))
                out_rb.append({
                    "criterion": crit,
                    "max_points": int(mp),
                    "points_awarded": int(pa),
                    "comment": " ".join(str(it.get("comment") or "").split()).strip() or None,
                })

        # Ensure rubric breakdown sums to score_points (best-effort)
        if out_rb:
            total_pa = sum(int(x.get("points_awarded", 0) or 0) for x in out_rb)
            if total_pa != sp:
                # adjust first item
                drift = sp - total_pa
                out_rb[0]["points_awarded"] = max(0, min(int(out_rb[0]["max_points"]), int(out_rb[0]["points_awarded"]) + drift))

        comment = " ".join(str(data.get("comment") or "").split()).strip()
        if not comment:
            comment = "Bài làm đã được chấm theo rubric."
        return {"score_points": sp, "comment": comment, "rubric_breakdown": out_rb}

    def _grade_offline(*, stem: str, rubric: List[Dict[str, Any]], max_points: int, answer_text: str, evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Deterministic fallback when no LLM is configured.
        return grade_essay_heuristic(
            stem=stem,
            answer_text=answer_text,
            rubric=rubric,
            max_points=max_points,
            evidence_chunks=evidence,
        )

    changed = False
    for item in bd:
        if (item.get("type") or "").lower() != "essay":
            continue
        if bool(item.get("graded")):
            continue
        if graded_count >= max_grade:
            break

        qid = int(item.get("question_id") or 0)
        q = qmap.get(qid)
        stem = (q.stem if q else item.get("stem") or item.get("question") or "") or ""
        stem = " ".join(str(stem).split()).strip()

        max_points = int((q.max_points if q else item.get("max_points", 10)) or 10)
        rubric = (q.rubric if q else item.get("rubric") or []) or []
        rubric = _sanitize_rubric(rubric, max_points=max_points)

        ans = (item.get("answer_text") or "").strip()
        if len(ans) < min_chars:
            item["score_points"] = 0
            item["comment"] = f"Câu trả lời quá ngắn (<{min_chars} ký tự). Hãy viết rõ ý theo rubric."
            item["graded"] = True
            item["rubric_breakdown"] = []
            changed = True
            graded_count += 1
            continue

        sources = (q.sources if q else None) or item.get("sources") or []
        evidence = _fetch_chunks_for_sources(sources)
        if use_llm:
            result = _grade_with_llm(stem=stem, rubric=rubric, max_points=max_points, answer_text=ans, evidence=evidence)
        else:
            result = grade_essay_heuristic(
                stem=stem,
                rubric=rubric,
                max_points=max_points,
                answer_text=ans,
                evidence_chunks=evidence,
            )

        item["score_points"] = int(result.get("score_points", 0) or 0)
        item["comment"] = result.get("comment")
        item["rubric_breakdown"] = result.get("rubric_breakdown") or []
        item["graded"] = True
        changed = True
        graded_count += 1

    if not changed:
        return None

    attempt.breakdown_json = bd
    flag_modified(attempt, "breakdown_json")

    split = _split_scores_from_breakdown(bd)
    attempt.score_percent = int(split["total_percent"])
    db.commit()
    db.refresh(attempt)

    return sync_diagnostic_from_attempt(db, quiz_set=quiz_set, attempt=attempt)


def _generate_essay_with_llm(requests: List[Dict[str, Any]], chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """LLM-based essay question generator, grounded to evidence chunks."""
    gen_mode = (settings.QUIZ_GEN_MODE or 'auto').strip().lower()
    if gen_mode == 'offline' or not llm_available():
        return []

    packed = pack_chunks(chunks, max_chunks=10)
    if not packed:
        return []

    lang = preferred_question_language(packed)

    valid_ids = [int(c['chunk_id']) for c in packed]

    def _tok(s: str) -> set[str]:
        return {w for w in re.findall(r"[\wÀ-ỹ]+", (s or '').lower()) if len(w) >= 3}

    def _best_sources(text_hint: str, k: int = 2) -> List[Dict[str, int]]:
        hint = _tok(text_hint)
        scored = []
        for c in packed:
            cid = int(c.get('chunk_id'))
            ct = _tok(f"{c.get('title') or ''} {c.get('text') or ''}")
            score = len(hint & ct)
            scored.append((score, cid))
        scored.sort(reverse=True)
        picked = [cid for score, cid in scored if score > 0][:k]
        if not picked:
            picked = [valid_ids[0]]
        return [{'chunk_id': int(x)} for x in picked]

    system = f"""Bạn là GIẢNG VIÊN RA ĐỀ + Assessment Agent.
    Nhiệm vụ: tạo bộ câu hỏi kiểm tra dựa CHỈ trên ngữ liệu được cung cấp (CONTEXT/TOPIC).
    Không copy nguyên văn; phải diễn đạt lại đúng tinh thần SGK/giáo viên (rõ ràng, sư phạm).

    NGÔN NGỮ ĐẦU RA: {lang.get('name','Vietnamese')}.
    - Tất cả stem/explanation/rubric phải dùng đúng ngôn ngữ này.
    - Không trộn ngôn ngữ (trừ thuật ngữ chuyên ngành bắt buộc).

    QUY TẮC CHỐNG "TÀI LIỆU PDF ẢNH/OCR LỖI":
    - Nếu CONTEXT bị rời rạc/đứt chữ/nhiều ký tự lỗi, hoặc thiếu thông tin để ra đề chắc chắn:
      => KHÔNG ĐƯỢC BỊA. Hãy trả về JSON với status="NEED_CLEAN_TEXT" và nêu reason ngắn + suggestion:
         "hãy upload file .docx hoặc pdf có text layer / bản copy text".
    - Chỉ khi CONTEXT đủ rõ mới sinh câu hỏi.

    CHẤT LƯỢNG CÂU HỎI (TỰ LUẬN):
    - Câu hỏi PHẢI ĐỘC LẬP (standalone): học sinh không cần mở/đọc tài liệu gốc vẫn làm được.
    - TUYỆT ĐỐI KHÔNG tham chiếu tài liệu: không nói "theo tài liệu", "trong đoạn/chương/trang/hình/bảng".
    - KHÔNG hỏi dạng đọc-hiểu theo câu chữ/chi tiết mặt chữ của tài liệu.
      Thay vào đó: yêu cầu giải thích bản chất, so sánh, lập luận, tình huống thực tiễn, phát hiện/sửa lỗi thường gặp.
    - Không trích nguyên văn; phải diễn đạt lại.
    - Ưu tiên yêu cầu lập luận/giải thích/so sánh/tình huống; tránh hỏi mẹo.
    - KHÔNG dùng một khung sẵn cứng nhắc. Hãy tự chọn góc hỏi dựa trên CONTEXT (công thức/quy trình/tiêu chí/ví dụ/lỗi thường gặp...).
    - Mỗi câu phải rõ ràng, không mơ hồ, không lỗi chính tả.
    - Mỗi câu phải có rubric chấm điểm; tổng points = max_points.

    BLOOM:
    - Mỗi câu gắn bloom_level ∈ {"remember","understand","apply","analyze","evaluate","create"}.
    - Với tự luận ưu tiên apply/analyze/evaluate/create theo request.target_bloom/level.

    BÁM NGUỒN:
    - evidence_chunks chỉ dùng để đảm bảo kiến thức nằm trong phạm vi đã học.
    - Mỗi câu phải có sources: mảng các chunk_id lấy từ evidence_chunks.
    - Không bịa kiến thức mâu thuẫn với CONTEXT.

    ĐẦU RA:
    - Chỉ xuất JSON hợp lệ, không thêm giải thích ngoài JSON.
    - Nếu OK: {"status":"OK","questions":[...]}.
    - Nếu CONTEXT lỗi/thiếu: {"status":"NEED_CLEAN_TEXT","reason":"...","suggestion":"..."}.
    """

    user = {
        'requests': requests,
        'language': lang,
        'evidence_chunks': packed,
        'constraints': [
            "Mỗi stem phải chứa topic trong dấu nháy đơn, ví dụ: Topic 'sql': ...",
            "Câu hỏi PHẢI ĐỘC LẬP (standalone): tự đủ ngữ cảnh; không tham chiếu 'tài liệu/văn bản/đoạn/chương/mục/trang/hình/bảng'.",
            "Không trích nguyên văn quá 8 từ liên tiếp từ evidence_chunks; phải diễn đạt lại.",
            "Stem 2–4 câu, có bối cảnh hoặc yêu cầu rõ ràng (giải thích/so sánh/tình huống/vận dụng).",
            "rubric là danh sách {criterion, points} và tổng points = max_points.",
            "sources BẮT BUỘC: mỗi câu có ít nhất 1 chunk_id từ evidence_chunks làm bằng chứng.",
            "Mỗi câu phải có bloom_level (apply/analyze/evaluate/create). Ưu tiên theo request.level/target_bloom nếu có.",
            "Các câu phải đa dạng và PHÙ HỢP nội dung thật sự trong CONTEXT: có thể hỏi quy trình/bước làm, tiêu chí/điều kiện, công thức & ý nghĩa, phân tích ví dụ, phát hiện/sửa sai lầm. Tránh lặp một khung cố định.",
        ],
        'output_format': {
            'questions': [
                {
                    'bloom_level': 'analyze',
                    'stem': 'string',
                    'explanation': 'string',
                    'max_points': 10,
                    'rubric': [{'criterion': '...', 'points': 4}],
                    'sources': [{'chunk_id': 123}],
                }
            ]
        },
    }

    try:
        data = chat_json(
            messages=[
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': __import__('json').dumps(user, ensure_ascii=False)},
            ],
            temperature=0.35,
            max_tokens=2400,
        )
    except Exception:
        return []

    # Respect OCR / low-signal contexts: do NOT hallucinate or fallback.
    if isinstance(data, dict) and str(data.get("status", "")).upper() == "NEED_CLEAN_TEXT":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "NEED_CLEAN_TEXT",
                "message": "CONTEXT không đủ rõ để sinh câu hỏi tự luận bám tài liệu.",
                "reason": data.get("reason") or data.get("message") or "CONTEXT bị rời rạc/ký tự lỗi hoặc thiếu thông tin chắc chắn.",
                "suggestion": data.get("suggestion") or "Hãy upload file .docx hoặc PDF có text layer / hoặc copy text của mục cần ra đề.",
            },
        )
    raw = data.get('questions') if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []

    out: List[Dict[str, Any]] = []
    for i, q in enumerate(raw):
        if not isinstance(q, dict):
            continue
        req = requests[i] if i < len(requests) else {}
        topic = (req.get('topic') or '').strip() or 'tài liệu'

        stem = _ensure_topic_in_essay_stem(' '.join(str(q.get('stem') or '').split()), topic)
        if len(stem) < 20:
            continue

        max_points = int(req.get('max_points', 10) or 10)
        rubric = _sanitize_rubric(q.get('rubric'), max_points=max_points)
        explanation = ' '.join(str(q.get('explanation') or '').split()).strip()
        if not explanation:
            explanation = 'Bài tự luận cần chấm theo rubric.'

        sources = q.get('sources')
        if isinstance(sources, dict):
            sources = [sources]
        # validate sources
        s_ok: List[Dict[str, int]] = []
        if isinstance(sources, list):
            for it in sources:
                cid = it.get('chunk_id') if isinstance(it, dict) else it
                try:
                    cid_i = int(cid)
                except Exception:
                    continue
                if cid_i in valid_ids:
                    s_ok.append({'chunk_id': cid_i})
        s_ok = s_ok[:2]
        if not s_ok:
            s_ok = _best_sources(f"{stem} {explanation}")

        raw_bloom = q.get('bloom_level') if isinstance(q, dict) else None
        if isinstance(raw_bloom, str) and raw_bloom.strip():
            bloom = normalize_bloom_level(raw_bloom)
        else:
            bloom = infer_bloom_level(f"{stem} {explanation}", default="analyze")

        out.append(
            {
                'type': 'essay',
                'bloom_level': bloom,
                'stem': stem,
                'options': [],
                'correct_index': -1,
                'explanation': explanation,
                'sources': s_ok,
                'max_points': int(max_points),
                'rubric': rubric,
            }
        )

    return out



def _collect_chunks(
    db: Session,
    *,
    topics: List[str],
    document_ids: List[int],
    level: str,
    need: int,
) -> List[Dict[str, Any]]:
    """Collect a pool of relevant chunks for assessment generation.

    Uses Corrective RAG (retrieve->grade->rewrite->retrieve) and filters out OCR-garbled text.
    """
    chunks: List[Dict[str, Any]] = []

    queries = [t for t in (topics or []) if (t or '').strip()]
    if not queries:
        queries = ['tổng hợp']

    # 0) Fast path: if selected topics match stored DocumentTopic titles, pull chunks directly
    # from the topic's chunk-range. This guarantees enough evidence per topic (even when
    # semantic retrieval is thin), and makes "đề tổng hợp" stable across difficulty levels.
    if document_ids:
        def _k(x: str) -> str:
            return ' '.join((x or '').lower().split())

        try:
            dts = (
                db.query(DocumentTopic)
                .filter(DocumentTopic.document_id.in_([int(x) for x in document_ids]))
                .all()
            )
        except Exception:
            dts = []

        by_title: Dict[str, List[DocumentTopic]] = {}
        for dt in dts:
            by_title.setdefault(_k(getattr(dt, 'title', '') or ''), []).append(dt)

        per_topic_limit = min(220, max(80, int(need) * 6))
        lens_cache: Dict[int, List[int]] = {}
        for t in queries[:10]:
            hits = by_title.get(_k(t), [])
            for dt in hits[:4]:
                if dt.start_chunk_index is None or dt.end_chunk_index is None:
                    continue

                # Expand evidence range ONLY for generation.
                doc_id = int(dt.document_id)
                if doc_id not in lens_cache:
                    len_rows = (
                        db.query(DocumentChunk.chunk_index, func.length(DocumentChunk.text))
                        .filter(DocumentChunk.document_id == doc_id)
                        .order_by(DocumentChunk.chunk_index.asc())
                        .all()
                    )
                    lens_cache[doc_id] = [int(r[1] or 0) for r in len_rows]

                (s2, e2) = ensure_topic_chunk_ranges_ready_for_quiz(
                    [(int(dt.start_chunk_index), int(dt.end_chunk_index))],
                    chunk_lengths=lens_cache[doc_id],
                )[0]
                rows = (
                    db.query(DocumentChunk)
                    .filter(DocumentChunk.document_id == doc_id)
                    .filter(DocumentChunk.chunk_index >= int(s2))
                    .filter(DocumentChunk.chunk_index <= int(e2))
                    .order_by(DocumentChunk.chunk_index.asc())
                    .limit(per_topic_limit)
                    .all()
                )
                for r in rows:
                    txt = r.text or ''
                    if not txt.strip():
                        continue
                    chunks.append({
                        'chunk_id': int(r.id),
                        'text': txt,
                        'document_id': int(r.document_id),
                        'document_title': str(r.document_id),
                        'score': 1.0,
                    })

    # Guard: cap number of retrieval queries.
    queries = queries[:6]
    top_k = min(80, max(10, int(need) * 4))

    for t in queries:
        query = _rag_query_for_topic(t, level)
        try:
            res = corrective_retrieve_and_log(
                db=db,
                query=query,
                top_k=top_k,
                filters={'document_ids': document_ids} if document_ids else None,
                topic=t,
            )
            chunks.extend(res.get('chunks', []) or [])
        except Exception:
            continue

    # Deduplicate by chunk_id
    uniq: Dict[int, Dict[str, Any]] = {}
    for c in chunks:
        try:
            cid = int(c.get('chunk_id'))
        except Exception:
            continue
        uniq[cid] = c
    chunks = list(uniq.values())

    # Normalize keys
    for c in chunks:
        if c.get('document_title') is None:
            c['document_title'] = c.get('title')
        if not (c.get('document_title') or '').strip():
            did = c.get('document_id')
            c['document_title'] = str(did) if did is not None else None

    # OCR/text-quality guard
    good, bad = filter_chunks_by_quality(chunks, min_score=float(settings.OCR_MIN_QUALITY_SCORE))
    bad_ratio = float(len(bad)) / float(max(1, len(chunks)))
    if (not good) or (bad_ratio >= float(settings.OCR_BAD_CHUNK_RATIO) and len(good) < 3):
        raise HTTPException(
            status_code=422,
            detail={
                'code': 'NEED_CLEAN_TEXT',
                'message': 'CONTEXT bị lỗi OCR / rời rạc nên không thể sinh đề bám tài liệu.',
                'reason': f'bad_chunk_ratio={bad_ratio:.2f}, good={len(good)}, total={len(chunks)}',
                'suggestion': 'Hãy upload file .docx hoặc PDF có text layer / hoặc copy-paste đúng mục cần ra đề.',
                'debug': {'sample_bad': bad[:2]},
            },
        )

    if good:
        chunks = good

    # Strip practice/answer-key lines so the exam generator doesn't copy from existing quizzes.
    cleaned_chunks = []
    for c in chunks:
        txt = clean_text_for_generation(str(c.get('text') or ''))
        if len(txt) >= 60:
            c2 = dict(c)
            c2['text'] = txt
            cleaned_chunks.append(c2)
    if cleaned_chunks:
        chunks = cleaned_chunks

    if chunks:
        return chunks

    # Fallback: if no retrieval result, pull raw chunks from DB (optionally by documents)
    # NOTE: still subject to OCR guard above; reaching here means retrieval returned none.
    q = db.query(DocumentChunk)
    if document_ids:
        q = q.filter(DocumentChunk.document_id.in_(document_ids))
    rows = q.order_by(DocumentChunk.created_at.desc()).limit(top_k).all()
    for r in rows:
        chunks.append({
            'chunk_id': r.id,
            'text': r.text,
            'document_id': r.document_id,
            'document_title': str(r.document_id),
            'score': 0.0,
        })
    # filter fallback chunks as well
    good2, _bad2 = filter_chunks_by_quality(chunks, min_score=float(settings.OCR_MIN_QUALITY_SCORE))
    return good2 or chunks



def _filter_semantic_duplicates(
    *,
    generated: List[Dict[str, Any]],
    excluded_stems: List[str],
    threshold: float = 0.85,
) -> tuple[List[Dict[str, Any]], int, str]:
    if not generated or not excluded_stems:
        return generated, 0, "none"

    q_texts = [str((q or {}).get("stem") or (q or {}).get("question", "")).strip() for q in generated]
    ex_texts = [str(x or "").strip() for x in excluded_stems if str(x or "").strip()]
    if not ex_texts:
        return generated, 0, "none"

    keep_idx = list(range(len(generated)))
    mode = "jaccard"

    try:
        emb_q = embed_texts(q_texts)
        emb_e = embed_texts(ex_texts)
        drop: set[int] = set()
        for i, vq in enumerate(emb_q):
            for ve in emb_e:
                if _cosine_similarity(vq, ve) > float(threshold):
                    drop.add(i)
                    break
        keep_idx = [i for i in range(len(generated)) if i not in drop]
        mode = "embedding"
    except Exception:
        drop = set()
        for i, stem in enumerate(q_texts):
            for ex in ex_texts:
                if _jaccard_similarity(stem, ex) > float(threshold):
                    drop.add(i)
                    break
        keep_idx = [i for i in range(len(generated)) if i not in drop]

    filtered = [generated[i] for i in keep_idx]
    removed = max(0, len(generated) - len(filtered))
    return filtered, removed, mode
def generate_assessment(
    db: Session,
    *,
    teacher_id: int,
    classroom_id: int,
    title: str,
    level: str,
    easy_count: int,
    medium_count: int = 0,
    hard_count: int,
    document_ids: List[int],
    topics: List[str],
    kind: str = "midterm",
    exclude_quiz_ids: List[int] | None = None,
    excluded_question_ids: List[int] | None = None,
    similarity_threshold: float = 0.72,
    time_limit_minutes: int | None = None,
    dedup_user_id: int | None = None,
    attempt_user_id: int | None = None,
) -> Dict[str, Any]:
    total_q = int(easy_count) + int(medium_count) + int(hard_count)

    if not _is_assessment_kind(kind):
        raise ValueError("Invalid kind")
    kind = _normalize_assessment_kind(kind)

    ensure_user_exists(db, int(teacher_id), role="teacher")

    _excluded_stems: set[str] = set()
    entry_topics: list[str] = []
    _excluded_question_ids = {int(x) for x in (excluded_question_ids or []) if x is not None}
    if exclude_quiz_ids:
        rows = db.query(Question.stem).filter(
            Question.quiz_set_id.in_([int(x) for x in exclude_quiz_ids])
        ).all()
        _excluded_stems.update({_normalize_stem_for_dedup(str(r[0] or "")) for r in rows if r and r[0]})
    if _excluded_question_ids:
        qrows = db.query(Question.stem).filter(Question.id.in_(list(_excluded_question_ids))).all()
        _excluded_stems.update({_normalize_stem_for_dedup(str(r[0] or "")) for r in qrows if r and r[0]})

    if kind == "final_exam":
        dedup_uid = int(dedup_user_id) if dedup_user_id is not None else int(teacher_id)
        entry_stems = get_used_question_stems(db, user_id=dedup_uid, kinds=["diagnostic_pre"])
        _excluded_stems.update(entry_stems)
        topic_rows = (
            db.query(QuizSet.topic)
            .join(Attempt, Attempt.quiz_set_id == QuizSet.id)
            .filter(Attempt.user_id == dedup_uid, QuizSet.kind.in_(["diagnostic_pre"]))
            .all()
        )
        entry_topics = sorted({str(r[0] or "").strip() for r in topic_rows if r and str(r[0] or "").strip()})
        if len(entry_stems) > 20:
            logging.getLogger(__name__).warning(
                "Final exam dedup excludes %s stems from diagnostic_pre; generation may be under-supplied",
                len(entry_stems),
            )

    _excluded_stems = {x for x in _excluded_stems if x}

    dedup_topics_from_entry: list[str] = []
    if kind == "final_exam":
        history_user_id = int(attempt_user_id if attempt_user_id is not None else teacher_id)
        prior_stems = get_used_question_stems(db, user_id=history_user_id, kinds=["diagnostic_pre", "entry_test"])
        _excluded_stems.update(prior_stems)
        if len(prior_stems) > 20:
            logging.getLogger(__name__).warning(
                "Large excluded stem set for final_exam: %s stems for user_id=%s",
                len(prior_stems),
                history_user_id,
            )
        topic_rows = (
            db.query(QuizSet.metadata_json)
            .join(Attempt, Attempt.quiz_set_id == QuizSet.id)
            .filter(Attempt.user_id == history_user_id, QuizSet.kind.in_(["diagnostic_pre", "entry_test", "final_exam"]))
            .all()
        )
        topic_seen: set[str] = set()
        for row in topic_rows:
            meta = row[0] if row else {}
            if isinstance(meta, dict):
                for t in (meta.get("topics_covered") or []):
                    tt = str(t or "").strip()
                    if tt:
                        topic_seen.add(tt)
        dedup_topics_from_entry = sorted(topic_seen)

    def _is_dup_local(stem: str) -> bool:
        return _is_dup(stem, _excluded_stems, similarity_threshold)

    # Auto-scope to teacher documents if UI did not pass document_ids
    doc_ids = list(document_ids or [])
    if not doc_ids:
        q = (" ".join([t for t in (topics or []) if (t or "").strip()]) or title or "tổng hợp").strip()
        auto = auto_document_ids_for_query(db, q, preferred_user_id=int(teacher_id), max_docs=5)
        if auto:
            doc_ids = auto
        else:
            doc_ids = [d.id for d in db.query(Document).filter(Document.user_id == int(teacher_id)).order_by(Document.created_at.desc()).limit(8).all()]

    chunks = _collect_chunks(db, topics=topics, document_ids=doc_ids, level=level, need=total_q)
    if not chunks:
        raise ValueError("No chunks available. Upload documents first.")

    # Build a sentence pool from chunks (for MCQ). Also keep mapping to a representative source.
    # Build a sentence pool from chunks. Guard against huge docs / too many topics.
    # A very large pool can spike memory and cause Docker to SIGKILL the backend.
    MAX_POOL = 6000
    pool: List[Dict[str, Any]] = []
    for c in chunks:
        text = c.get("text") or ""
        for s in _pick_sentences(text):
            pool.append({
                "sentence": s,
                "source": {
                    "chunk_id": int(c.get("chunk_id")),
                    "document_id": int(c.get("document_id")) if c.get("document_id") is not None else None,
                    "document_title": c.get("document_title"),
                    "score": float(c.get("score", 0.0)),
                    "preview": _truncate(text, 160),
                },
            })
            if len(pool) >= MAX_POOL:
                break
        if len(pool) >= MAX_POOL:
            break

    if len(pool) < 4:
        # If the document is too short, create synthetic options from chunk previews
        pool = [{
            "sentence": _truncate(c.get("text") or "", 140),
            "source": {
                "chunk_id": int(c.get("chunk_id")),
                "document_id": int(c.get("document_id")) if c.get("document_id") is not None else None,
                "document_title": c.get("document_title"),
                "score": float(c.get("score", 0.0)),
                "preview": _truncate(c.get("text") or "", 160),
            },
        } for c in chunks if (c.get("text") or "").strip()][:MAX_POOL]

    if len(pool) < 4:
        raise ValueError("Not enough content to generate MCQ. Upload a longer document.")

    random.shuffle(pool)

    topics_cycle = [t.strip() for t in (topics or []) if (t or '').strip()]
    if not topics_cycle:
        topics_cycle = [((title or 'tài liệu').strip() or 'tài liệu')]

    generated: List[Dict[str, Any]] = []
    used_idx = 0

    def _normalize_question_bloom(q: Dict[str, Any], allowed: set[str], fallback_cycle: list[str], index_hint: int = 0) -> Dict[str, Any]:
        qq = dict(q or {})
        raw = qq.get("bloom_level")
        bloom = normalize_bloom_level(raw)
        if not bloom or bloom not in allowed:
            inferred = normalize_bloom_level(infer_bloom_level(str(qq.get("stem") or ""), str(qq.get("explanation") or "")))
            bloom = inferred if inferred in allowed else fallback_cycle[index_hint % max(1, len(fallback_cycle))]
        qq["bloom_level"] = bloom
        return qq

    # Easy/Medium MCQ
    # Prefer LLM-based MCQs when available (more natural, less "chọn câu trích" style).
    gen_mode = (settings.QUIZ_GEN_MODE or "auto").strip().lower()
    def _generate_mcq_bucket(*, count: int, bucket_name: str, target_blooms: list[str], excluded_stems: set[str] | None = None) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if int(count) <= 0:
            return out
        allowed = set(target_blooms)
        llm_mcqs: List[Dict[str, Any]] = []
        if gen_mode in {"auto", "llm"} and llm_available():
            topic_list = topics_cycle
            base = int(count) // max(1, len(topic_list))
            rem = int(count) % max(1, len(topic_list))
            for idx, t in enumerate(topic_list):
                cnt = base + (1 if idx < rem else 0)
                if cnt <= 0:
                    continue
                try:
                    hint = None
                    if int(medium_count) > 0:
                        hint = (
                            f"TARGET_DIFFICULTY={bucket_name.upper()} - ưu tiên Bloom levels: {', '.join(target_blooms)}. "
                            "Không dùng mức ngoài nhóm mục tiêu nếu không thật sự cần thiết."
                        )
                    if (kind or "").lower() == "final_exam" and (_excluded_question_ids or _excluded_stems):
                        final_rules = (
                            "QUAN TRỌNG: Đây là bài kiểm tra CUỐI KỲ. Câu hỏi phải: "
                            "1) KHÔNG trùng bài đầu vào; "
                            "2) ưu tiên Bloom apply/analyze/evaluate/create; "
                            "3) tập trung ứng dụng thực tế, so sánh, phân tích; "
                            "4) tối thiểu 40% câu dạng scenario-based."
                        )
                        hint = (hint + "\n" + final_rules) if hint else final_rules
                    qs = _generate_mcq_with_llm(
                        t,
                        level,
                        cnt,
                        chunks,
                        extra_system_hint=hint,
                    )
                except HTTPException:
                    raise
                except Exception:
                    qs = []
                llm_mcqs.extend(qs or [])

        if llm_mcqs:
            random.shuffle(llm_mcqs)
            for i, q in enumerate(llm_mcqs):
                stem = str((q or {}).get("stem") or (q or {}).get("question", ""))
                if _is_dup(stem, excluded_stems, similarity_threshold):
                    continue
                out.append(_normalize_question_bloom(q, allowed, target_blooms, i))
                if len(out) >= int(count):
                    break
            return out[: int(count)]

        offline_mcqs: List[Dict[str, Any]] = []
        topic_list = topics_cycle
        base = int(count) // max(1, len(topic_list))
        rem = int(count) % max(1, len(topic_list))
        for idx, t in enumerate(topic_list):
            cnt = base + (1 if idx < rem else 0)
            if cnt <= 0:
                continue
            try:
                offline_mcqs.extend(_generate_mcq_from_chunks(t, level, cnt, chunks, excluded_question_ids=excluded_question_ids) or [])
            except Exception:
                continue

        random.shuffle(offline_mcqs)
        for i, q in enumerate(offline_mcqs):
            stem = str((q or {}).get("stem") or (q or {}).get("question", ""))
            if _is_dup(stem, excluded_stems, similarity_threshold):
                continue
            out.append(_normalize_question_bloom(q, allowed, target_blooms, i))
            if len(out) >= int(count):
                break

        if len(out) < int(count):
            for i in range(len(out), int(count)):
                nonlocal used_idx
                if used_idx >= len(pool):
                    used_idx = 0
                correct = pool[used_idx]
                used_idx += 1
                others = [p["sentence"] for p in pool if p["sentence"] != correct["sentence"]]
                if len(others) < 3:
                    others = (others * 3)[:3]
                distractors = random.sample(others, k=3)
                topic_for_q = topics_cycle[i % len(topics_cycle)]
                q = _build_mcq_question(
                    topic=topic_for_q,
                    correct_sentence=correct["sentence"],
                    distractors=distractors,
                    source=correct["source"],
                )
                stem = str((q or {}).get("stem") or (q or {}).get("question", ""))
                if _is_dup(stem, excluded_stems, similarity_threshold):
                    continue
                out.append(_normalize_question_bloom(q, allowed, target_blooms, i))
        return out[: int(count)]

    bucket_excluded_stems = _excluded_stems if kind == "final_exam" else None
    easy_mcqs = _generate_mcq_bucket(count=int(easy_count), bucket_name="easy", target_blooms=["remember", "understand"], excluded_stems=bucket_excluded_stems)
    medium_mcqs = _generate_mcq_bucket(count=int(medium_count), bucket_name="medium", target_blooms=["apply", "analyze"], excluded_stems=bucket_excluded_stems)
    generated.extend(easy_mcqs)
    generated.extend(medium_mcqs)

    # Clean/filter MCQ questions to keep options/stems demo-friendly (dedup + sanitize)
    if generated:
        mcqs = [q for q in generated if (q.get("type") or "").lower() == "mcq"]
        others = [q for q in generated if (q.get("type") or "").lower() != "mcq"]
        mcq_target_total = int(easy_count) + int(medium_count)
        mcqs = clean_mcq_questions(mcqs, limit=mcq_target_total)

        # Optional LLM editor pass for MCQs (improves stems/distractors/explanations).
        # Uses the same heuristic/config as /quiz/generate.
        if mcqs and _quiz_refine_enabled(questions=mcqs, gen_mode=gen_mode):
            try:
                mcqs = _llm_refine_mcqs(topic=(title or "bài kiểm tra"), level=level, chunks=chunks, questions=mcqs)
                mcqs = clean_mcq_questions(mcqs, limit=mcq_target_total)
            except Exception:
                mcqs = clean_mcq_questions(mcqs, limit=mcq_target_total)
        generated = mcqs + others

    # Diagnostic: 2 essay levels (Intermediate + Advanced) để phân tầng tốt hơn
    if (kind or "").lower() in ("diagnostic_pre", "diagnostic_post") and int(hard_count) >= 2:
        essay_levels = ["intermediate", "advanced"] + ["advanced"] * max(0, int(hard_count) - 2)
    else:
        essay_levels = [level] * int(hard_count)

    # Build essay requests (topic + level) so the LLM can generate diverse, grounded prompts
    essay_reqs: List[Dict[str, Any]] = []
    for i in range(int(hard_count)):
        topic_for_q = topics_cycle[i % len(topics_cycle)]
        lvl_for_q = essay_levels[i] if i < len(essay_levels) else level
        lv0 = (lvl_for_q or "").strip().lower()
        target_bloom = "evaluate" if (i % 2 == 0) else "create"
        essay_reqs.append({"topic": topic_for_q, "level": lvl_for_q, "max_points": 10, "target_bloom": target_bloom})

    essay_generated: List[Dict[str, Any]] = []
    gen_mode = (settings.QUIZ_GEN_MODE or "auto").strip().lower()
    if gen_mode in {"auto", "llm"} and llm_available():
        try:
            essay_generated = _generate_essay_with_llm(essay_reqs, chunks) or []
        except HTTPException:
            raise
        except Exception:
            essay_generated = []

    # If LLM returns too few, fill the rest using template questions
    need_essays = int(hard_count)
    for i, q in enumerate((essay_generated or [])[:need_essays]):
        qq = dict(q or {})
        qq["type"] = "essay"
        qq["bloom_level"] = normalize_bloom_level(qq.get("bloom_level")) if normalize_bloom_level(qq.get("bloom_level")) in {"evaluate", "create"} else ("evaluate" if i % 2 == 0 else "create")
        generated.append(qq)

    missing = need_essays - len([q for q in generated if (q.get("type") or "").lower() == "essay"])
    if missing > 0:
        # Fallback: per-topic template essay questions + a relevant source chunk
        for j in range(missing):
            i = (len(essay_generated) + j)
            topic_for_q = topics_cycle[i % len(topics_cycle)]
            lvl_for_q = essay_levels[i] if i < len(essay_levels) else level
            source = _pick_source_for_topic(db, topic=topic_for_q, level=lvl_for_q, document_ids=document_ids)
            qq = _build_essay_question(topic=topic_for_q, level=lvl_for_q, source=source)
            qq["type"] = "essay"
            qq["bloom_level"] = "evaluate" if (j % 2 == 0) else "create"
            generated.append(qq)

    def _bucket_counts(questions: List[Dict[str, Any]]) -> Dict[str, int]:
        counts = {"easy": 0, "medium": 0, "hard": 0}
        for q in (questions or []):
            qtype = str((q or {}).get("type") or "").strip().lower()
            bloom = normalize_bloom_level((q or {}).get("bloom_level"))
            if qtype == "essay" and bloom in {"evaluate", "create"}:
                counts["hard"] += 1
            elif bloom in {"remember", "understand"}:
                counts["easy"] += 1
            elif bloom in {"apply", "analyze"}:
                counts["medium"] += 1
        return counts

    # Validate and re-sample per difficulty bucket if one group is short.
    desired = {"easy": int(easy_count), "medium": int(medium_count), "hard": int(hard_count)}
    current = _bucket_counts(generated)
    if current["easy"] < desired["easy"]:
        generated.extend(
            _generate_mcq_bucket(
                count=desired["easy"] - current["easy"],
                bucket_name="easy",
                target_blooms=["remember", "understand"],
                excluded_stems=bucket_excluded_stems,
            )
        )
    current = _bucket_counts(generated)
    if current["medium"] < desired["medium"]:
        generated.extend(
            _generate_mcq_bucket(
                count=desired["medium"] - current["medium"],
                bucket_name="medium",
                target_blooms=["apply", "analyze"],
                excluded_stems=bucket_excluded_stems,
            )
        )
    current = _bucket_counts(generated)
    if current["hard"] < desired["hard"]:
        for j in range(desired["hard"] - current["hard"]):
            topic_for_q = topics_cycle[j % len(topics_cycle)]
            source = _pick_source_for_topic(db, topic=topic_for_q, level=level, document_ids=document_ids)
            qq = _build_essay_question(topic=topic_for_q, level=level, source=source)
            qq["type"] = "essay"
            qq["bloom_level"] = "evaluate" if (j % 2 == 0) else "create"
            generated.append(qq)

    
    # Optional LLM editor pass for essay questions (improves teacher-like prompts + rubric).
    gen_mode2 = (settings.QUIZ_GEN_MODE or "auto").strip().lower()
    essays = [q for q in (generated or []) if (q.get("type") or "").lower() == "essay"]
    if essays and _essay_refine_enabled(questions=essays, gen_mode=gen_mode2):
        try:
            refined = _llm_refine_essays(topic=(title or "bài kiểm tra"), level=level, chunks=chunks, questions=essays)
            # Replace essays in-place while preserving the original order in `generated`
            it = iter(refined or [])
            new_gen: List[Dict[str, Any]] = []
            for q in (generated or []):
                if (q.get("type") or "").lower() == "essay":
                    try:
                        new_gen.append(next(it))
                    except StopIteration:
                        new_gen.append(q)
                else:
                    new_gen.append(q)
            generated = new_gen
        except HTTPException:
            raise
        except Exception:
            pass

    # Filter out stems that overlap with excluded assessments.
    original_count = len(generated)
    generated = [q for q in generated if not _is_dup_local(str((q or {}).get("stem") or (q or {}).get("question", "")))]
    filtered_count = max(0, original_count - len(generated))

    # Semantic duplicate guard (embedding cosine, fallback jaccard).
    semantic_filtered = 0
    semantic_mode = "none"
    generated, semantic_filtered, semantic_mode = _filter_semantic_duplicates(
        generated=generated,
        excluded_stems=sorted(_excluded_stems),
        threshold=0.85,
    )
    filtered_count += int(semantic_filtered)

    if filtered_count > 0:
        logging.getLogger(__name__).info(
            "Filtered %s/%s duplicate questions (similarity >= %s, semantic=%s, semantic_mode=%s)",
            filtered_count,
            original_count,
            float(similarity_threshold),
            int(semantic_filtered),
            semantic_mode,
        )

    target_total = int(easy_count) + int(medium_count) + int(hard_count)
    deficit = target_total - len(generated)
    if deficit > 0 and llm_available():
        extra_system_hint = (
            f"QUAN TRỌNG: Hệ thống đã loại {deficit} câu bị trùng với bài trước. "
            f"Hãy tạo {deficit} câu HOÀN TOÀN MỚI, tiếp cận topic từ góc độ khác: "
            "ứng dụng thực tế, bài toán ngược, hoặc kết hợp nhiều khái niệm."
        )
        topic_list = topics_cycle or [((title or "tài liệu").strip() or "tài liệu")]
        extra_qs: List[Dict[str, Any]] = []
        for idx, topic_name in enumerate(topic_list):
            if len(extra_qs) >= deficit:
                break
            remain = deficit - len(extra_qs)
            slots_left = max(1, len(topic_list) - idx)
            per_topic = max(1, (remain + slots_left - 1) // slots_left)
            try:
                more = _generate_mcq_with_llm(
                    topic_name,
                    level,
                    per_topic,
                    chunks,
                    extra_system_hint=extra_system_hint,
                )
            except HTTPException:
                raise
            except Exception:
                more = []
            extra_qs.extend(more or [])

        extra_qs = [q for q in (extra_qs or []) if not _is_dup_local(str((q or {}).get("stem") or (q or {}).get("question", "")))]
        if extra_qs:
            generated.extend(extra_qs[:deficit])

    if len(generated) > target_total:
        generated = generated[:target_total]

    if kind == "final_exam":
        essay_count = sum(1 for q in (generated or []) if str((q or {}).get("type") or "").strip().lower() == "essay")
        if essay_count < 2:
            topic_fallback = (topics_cycle[0] if topics_cycle else (title or "Final Exam"))
            for i in range(2 - essay_count):
                generated.append(
                    {
                        "type": "essay",
                        "bloom_level": "evaluate",
                        "stem": f"Phân tích và đề xuất giải pháp nâng cao cho chủ đề '{topic_fallback}' (câu tự luận bắt buộc {i+1}).",
                        "options": [],
                        "correct_index": 0,
                        "explanation": "Đánh giá theo rubric.",
                        "sources": [],
                        "max_points": 10,
                        "rubric": [
                            {"criterion": "Độ chính xác kiến thức", "points": 4},
                            {"criterion": "Lập luận & ví dụ", "points": 4},
                            {"criterion": "Trình bày", "points": 2},
                        ],
                    }
                )
            generated = generated[:target_total]

    # -------------------------
    # Estimate time per question (minutes)
    # -------------------------
    try:
        minutes = _estimate_minutes_llm(questions=[q for q in (generated or []) if isinstance(q, dict)], level=level)
    except Exception:
        minutes = None
    if not minutes:
        minutes = [_heuristic_estimated_minutes(q, level=level) for q in (generated or []) if isinstance(q, dict)]

    # Attach to the generated question dicts (aligned by order)
    mi = 0
    for q in (generated or []):
        if not isinstance(q, dict):
            continue
        try:
            q["estimated_minutes"] = int(minutes[mi]) if mi < len(minutes) else int(_heuristic_estimated_minutes(q, level=level))
        except Exception:
            q["estimated_minutes"] = int(_heuristic_estimated_minutes(q, level=level))
        mi += 1

# Persist as a QuizSet(kind="midterm"/"diagnostic_pre"/"diagnostic_post") + questions
    kind = _normalize_assessment_kind(kind)
    quiz_set = QuizSet(user_id=teacher_id, kind=kind, topic=title, level=level, source_query_id=None, excluded_from_quiz_ids=[int(x) for x in (exclude_quiz_ids or [])], generation_seed=None)
    seed_payload = {"teacher_id": int(teacher_id), "title": str(title), "topics": [str(t).strip().lower() for t in (topics or []) if str(t).strip()], "kind": kind, "doc_ids": [int(x) for x in (doc_ids or [])], "excluded_question_ids": sorted(list(_excluded_question_ids))}
    quiz_set.generation_seed = __import__("hashlib").sha256(json.dumps(seed_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    topics_covered = [t.strip() for t in (topics or []) if (t or "").strip()]
    quiz_metadata: Dict[str, Any] = {}
    if kind in {"entry_test", "diagnostic_pre", "final_exam"}:
        quiz_metadata["topics_covered"] = topics_covered
    if kind == "final_exam":
        quiz_metadata["deduplication_info"] = {
            "excluded_count": int(len(_excluded_stems)),
            "topics_from_entry": dedup_topics_from_entry,
        }

    computed_total_minutes = 0
    try:
        computed_total_minutes = sum(int((q.get("estimated_minutes") or 0)) for q in (generated or []) if isinstance(q, dict))
    except Exception:
        computed_total_minutes = 0

    requested_minutes = int(time_limit_minutes) if time_limit_minutes is not None else int(computed_total_minutes)
    requested_minutes = max(1, requested_minutes)

    quiz_set = QuizSet(
        user_id=teacher_id,
        kind=kind,
        topic=title,
        level=level,
        duration_seconds=int(requested_minutes * 60),
        metadata_json=quiz_metadata,
        source_query_id=None,
    )
    db.add(quiz_set)
    db.commit()
    db.refresh(quiz_set)

    # Link this assessment to a classroom (so each class has its own tests)
    db.add(
        ClassroomAssessment(
            classroom_id=int(classroom_id),
            assessment_id=int(quiz_set.id),
            kind=kind,
            visible_to_students=True,
        )
    )
    db.flush()

    questions_out = []
    for idx, q in enumerate(generated, start=1):
        row = Question(
            quiz_set_id=quiz_set.id,
            order_no=idx,
            type=q["type"],
            bloom_level=normalize_bloom_level(q.get("bloom_level")) if isinstance(q, dict) else "understand",
            stem=q["stem"],
            options=q.get("options", []),
            correct_index=int(q.get("correct_index", 0)),
            explanation=q.get("explanation"),
            estimated_minutes=int(q.get("estimated_minutes") or 0),
            sources=q.get("sources", []),
            max_points=int(q.get("max_points", 0)),
            rubric=q.get("rubric", []),
        )
        db.add(row)
        db.flush()  # get row.id

        questions_out.append({
            "question_id": row.id,
            "type": row.type,
            "bloom_level": row.bloom_level,
            "stem": row.stem,
            "options": row.options or [],
            "max_points": int(row.max_points or 0),
            "rubric": row.rubric or [],
            "sources": row.sources or [],
            "estimated_minutes": int(getattr(row, "estimated_minutes", 0) or 0),
        })

    db.commit()

    total_minutes = int(requested_minutes)

    difficulty_plan = {"easy": 0, "medium": 0, "hard": 0}
    for q in (questions_out or []):
        qtype = str((q or {}).get("type") or "").strip().lower()
        bloom = normalize_bloom_level((q or {}).get("bloom_level"))
        if qtype == "essay" and bloom in {"evaluate", "create"}:
            difficulty_plan["hard"] += 1
        elif bloom in {"remember", "understand"}:
            difficulty_plan["easy"] += 1
        elif bloom in {"apply", "analyze"}:
            difficulty_plan["medium"] += 1

    return {
        "assessment_id": quiz_set.id,
        "title": quiz_set.topic,
        "level": quiz_set.level,
        "time_limit_minutes": int(total_minutes),
        "metadata": quiz_metadata,
        "questions": questions_out,
        "difficulty_plan": difficulty_plan,
        "excluded_stems_count": len(_excluded_stems),
        "filtered_duplicates": int(filtered_count),
        "semantic_filtered_duplicates": int(semantic_filtered),
        "semantic_filter_mode": semantic_mode,
        "deduplication_info": {
            "excluded_count": len(_excluded_stems),
            "topics_from_entry": entry_topics,
            "excluded_count": int(len(_excluded_stems)),
            "topics_from_entry": dedup_topics_from_entry,
        },
    }


def get_assessment(db: Session, *, assessment_id: int) -> Dict[str, Any]:
    quiz_set = db.query(QuizSet).filter(QuizSet.id == assessment_id).first()
    if not quiz_set or (not _is_assessment_kind(quiz_set.kind)):
        raise ValueError("Assessment not found")

    questions = (
        db.query(Question)
        .filter(Question.quiz_set_id == assessment_id)
        .order_by(Question.order_no.asc())
        .all()
    )

    total_minutes = max(0, int((getattr(quiz_set, "duration_seconds", 0) or 0) // 60))

    # Backfill for older assessments that were created before we stored estimated_minutes.
    if total_minutes <= 0 and questions:
        try:
            # Prepare dicts for the estimator
            qdicts: List[Dict[str, Any]] = []
            for q in questions:
                qdicts.append(
                    {
                        "type": q.type,
                        "bloom_level": getattr(q, "bloom_level", None),
                        "max_points": int(q.max_points or 0),
                        "stem": q.stem,
                    }
                )

            mins = _estimate_minutes_llm(questions=qdicts, level=str(getattr(quiz_set, "level", "beginner") or "beginner"))
            if not mins:
                mins = [_heuristic_estimated_minutes(qd, level=str(getattr(quiz_set, "level", "beginner") or "beginner")) for qd in qdicts]

            # Only fill missing (<=0)
            for q, m in zip(questions, mins):
                try:
                    if int(getattr(q, "estimated_minutes", 0) or 0) <= 0:
                        q.estimated_minutes = int(m)
                except Exception:
                    pass
            db.commit()

            total_minutes = sum(int(getattr(q, "estimated_minutes", 0) or 0) for q in (questions or []))
        except Exception:
            # ignore
            pass

    return {
        "assessment_id": quiz_set.id,
        "title": quiz_set.topic,
        "level": quiz_set.level,
        "kind": quiz_set.kind,
        "metadata": getattr(quiz_set, "metadata_json", {}) or {},
        "time_limit_minutes": int(total_minutes),
        "questions": [
            {
                "question_id": q.id,
                "type": q.type,
                "bloom_level": getattr(q, "bloom_level", None),
                "stem": q.stem,
                "options": q.options or [],
                "max_points": int(q.max_points or 0),
                "rubric": q.rubric or [],
                "sources": q.sources or [],
                "estimated_minutes": int(getattr(q, "estimated_minutes", 0) or 0),
            }
            for q in questions
        ],
    }


def generate_final_exam(
    db: Session,
    *,
    user_id: int,
    document_id: int,
    topic_ids: list[int],
    classroom_id: int = 0,
    title: str = "Final Exam",
) -> Dict[str, Any]:
    """Generate final exam with strict deduplication against diagnostic_pre."""

    pre_exam_ids = [
        int(r[0])
        for r in (
            db.query(QuizSet.id)
            .filter(QuizSet.user_id == int(user_id), QuizSet.kind == "diagnostic_pre")
            .all()
        )
    ]

    topics = [
        str(r[0]).strip()
        for r in (
            db.query(DocumentTopic.title)
            .filter(DocumentTopic.id.in_([int(t) for t in (topic_ids or [])]))
            .all()
        )
        if r and str(r[0] or "").strip()
    ]

    if not topics:
        raise ValueError("No valid topics found for final exam")

    return generate_assessment(
        db,
        teacher_id=int(user_id),
        classroom_id=int(classroom_id),
        title=str(title or "Final Exam"),
        level="intermediate",
        easy_count=4,
        medium_count=8,
        hard_count=8,
        document_ids=[int(document_id)],
        topics=topics,
        kind="final_exam",
        exclude_quiz_ids=pre_exam_ids,
        time_limit_minutes=60,
    )


def _topic_percent_map_from_attempt(attempt: Attempt | None) -> Dict[str, int]:
    if not attempt:
        return {}
    topic_scores: Dict[str, list[int]] = {}
    for item in (attempt.breakdown_json or []):
        topic = str(item.get("topic") or "").strip().lower()
        if not topic:
            continue
        max_points = int(item.get("max_points") or 0)
        if max_points <= 0:
            continue
        score_points = int(item.get("score_points") or 0)
        bucket = topic_scores.setdefault(topic, [0, 0])
        bucket[0] += score_points
        bucket[1] += max_points

    out: Dict[str, int] = {}
    for topic, (earned, total) in topic_scores.items():
        out[topic] = int(round((earned / max(1, total)) * 100))
    return out


def _final_improvement_payload(db: Session, *, user_id: int, final_attempt: Attempt) -> Dict[str, Any]:
    pre_attempt = (
        db.query(Attempt)
        .join(QuizSet, QuizSet.id == Attempt.quiz_set_id)
        .filter(Attempt.user_id == int(user_id), QuizSet.kind == "diagnostic_pre")
        .order_by(Attempt.created_at.desc())
        .first()
    )
    if not pre_attempt:
        return {
            "improvement_vs_entry": None,
            "topics_improved": [],
            "topics_declined": [],
        }

    pre_score = int(getattr(pre_attempt, "score_percent", 0) or 0)
    final_score = int(getattr(final_attempt, "score_percent", 0) or 0)
    pre_topics = _topic_percent_map_from_attempt(pre_attempt)
    final_topics = _topic_percent_map_from_attempt(final_attempt)

    topics_improved: list[str] = []
    topics_declined: list[str] = []
    for topic in sorted(set(pre_topics.keys()) | set(final_topics.keys())):
        delta = int(final_topics.get(topic, 0)) - int(pre_topics.get(topic, 0))
        if delta > 0:
            topics_improved.append(topic)
        elif delta < 0:
            topics_declined.append(topic)

    return {
        "improvement_vs_entry": int(final_score - pre_score),
        "topics_improved": topics_improved,
        "topics_declined": topics_declined,
    }

def submit_assessment(db: Session, *, assessment_id: int, user_id: int, duration_sec: int,
                      answers: List[Dict[str, Any]]) -> Dict[str, Any]:
    quiz_set = db.query(QuizSet).filter(QuizSet.id == assessment_id).first()
    if not quiz_set or (not _is_assessment_kind(quiz_set.kind)):
        raise ValueError("Assessment not found")

    # Demo-friendly: allow any numeric user_id from the UI; auto-create if missing.
    ensure_user_exists(db, int(user_id), role="student")

    questions = (
        db.query(Question)
        .filter(Question.quiz_set_id == assessment_id)
        .order_by(Question.order_no.asc())
        .all()
    )

    answer_map = {int(a.get("question_id")): a for a in (answers or [])}

    breakdown: List[Dict[str, Any]] = []

    mcq_earned = 0
    mcq_total = 0

    has_essay = False

    for q in questions:
        a = answer_map.get(q.id, {})
        topic = _infer_topic_from_stem(q.stem, fallback=str(quiz_set.topic))

        if q.type == "mcq":
            mcq_total += 1
            chosen = a.get("answer_index")
            try:
                chosen_i = int(chosen)
            except Exception:
                chosen_i = -1

            is_correct = chosen_i == int(q.correct_index)
            score_points = 1 if is_correct else 0
            mcq_earned += score_points

            breakdown.append({
                "question_id": q.id,
                "type": "mcq",
                "topic": topic,
                "chosen": chosen_i,
                "correct": int(q.correct_index),
                "is_correct": bool(is_correct),
                "score_points": int(score_points),
                "max_points": 1,
                "explanation": q.explanation,
                "sources": q.sources or [],
                "graded": True,
            })
        else:
            has_essay = True
            txt = (a.get("answer_text") or "").strip()
            breakdown.append({
                "question_id": q.id,
                "type": "essay",
                "topic": topic,
                "answer_text": txt,
                "score_points": 0,
                "max_points": int(q.max_points or 10),
                "rubric": q.rubric or [],
                "explanation": q.explanation or None,
                "comment": None,
                "graded": False,
                "rubric_breakdown": [],
                "sources": q.sources or [],
            })

    mcq_percent = int(round((mcq_earned / mcq_total) * 100)) if mcq_total else 0

    # Khi essay chưa chấm, tạm thời dùng điểm MCQ để hiển thị ngay.
    score_percent = int(mcq_percent)

    attempt = Attempt(
        user_id=user_id,
        quiz_set_id=assessment_id,
        score_percent=score_percent,
        duration_sec=duration_sec or 0,
        answers_json=answers or [],
        breakdown_json=breakdown,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    # Auto-grade essay answers (LLM) so students can get results without teacher grading.
    synced_diagnostic = None
    if has_essay and _essay_autograde_enabled():
        try:
            synced_diagnostic = _auto_grade_essays_for_attempt(db, quiz_set=quiz_set, attempt=attempt)
        except Exception:
            synced_diagnostic = None

    bd = list(attempt.breakdown_json or [])
    split = _split_scores_from_breakdown(bd)
    pending = any((i.get("type") == "essay" and not i.get("graded")) for i in bd)

    score_percent = int(attempt.score_percent)
    total_percent = int(split["total_percent"]) if not pending else int(score_percent)

    earned_points = int(split["mcq_earned"]) + int(split["essay_earned"])
    total_points = int(split["mcq_total"]) + int(split["essay_total"])
    classroom_link = (
        db.query(ClassroomAssessment)
        .filter(ClassroomAssessment.assessment_id == int(assessment_id))
        .order_by(ClassroomAssessment.id.asc())
        .first()
    )

    result = {
        "assessment_id": assessment_id,
        "assessment_kind": _normalize_assessment_kind(getattr(quiz_set, "kind", None)),
        "classroom_id": int(getattr(classroom_link, "classroom_id", 0) or 0),
        "attempt_id": attempt.id,
        "duration_sec": int(getattr(attempt, "duration_sec", 0) or 0),
        "score_percent": score_percent,
        "mcq_score_percent": int(split["mcq_percent"]),
        "essay_score_percent": int(split["essay_percent"]),
        "total_score_percent": total_percent,
        "score_points": earned_points,
        "max_points": total_points,
        "status": "submitted (essay pending)" if pending else "graded",
        "breakdown": bd,
        "answer_review": _build_answer_review(breakdown=bd, questions=questions, default_topic=str(quiz_set.topic or "tài liệu")),
        "synced_diagnostic": synced_diagnostic,
    }
    if _normalize_assessment_kind(getattr(quiz_set, "kind", None)) == "final_exam":
        result.update(_final_improvement_payload(db, user_id=int(user_id), final_attempt=attempt))
    return result
def list_assessments_for_teacher(db: Session, *, teacher_id: int, classroom_id: int | None = None) -> List[Dict[str, Any]]:
    """List assessments created by a teacher, scoped to classroom when provided."""

    q = (
        db.query(QuizSet, ClassroomAssessment.classroom_id)
        .join(ClassroomAssessment, ClassroomAssessment.assessment_id == QuizSet.id)
        .filter(QuizSet.user_id == int(teacher_id))
        .filter(QuizSet.kind.in_(["midterm", "diagnostic_pre", "diagnostic_post", "assessment", "entry_test", "final_exam"]))
    )
    if classroom_id is not None:
        q = q.filter(ClassroomAssessment.classroom_id == int(classroom_id))
    rows = q.order_by(QuizSet.created_at.desc()).all()

    return [
        {
            "assessment_id": r[0].id,
            "classroom_id": int(r[1]),
            "title": r[0].topic,
            "level": r[0].level,
            "kind": _normalize_assessment_kind(r[0].kind),
            "created_at": r[0].created_at.isoformat(),
        }
        for r in rows
    ]



def list_assessments_for_user(db: Session, *, user_id: int, classroom_id: int | None = None) -> List[Dict[str, Any]]:
    """List assessments available to a student (via classroom membership)."""

    q = (
        db.query(QuizSet, ClassroomAssessment.classroom_id)
        .join(ClassroomAssessment, ClassroomAssessment.assessment_id == QuizSet.id)
        .join(ClassroomMember, ClassroomMember.classroom_id == ClassroomAssessment.classroom_id)
        .filter(ClassroomMember.user_id == int(user_id))
        .filter(ClassroomAssessment.visible_to_students.is_(True))
        .filter(QuizSet.kind.in_(["midterm", "diagnostic_pre", "diagnostic_post", "assessment", "entry_test", "final_exam"]))
    )
    if classroom_id is not None:
        q = q.filter(ClassroomAssessment.classroom_id == int(classroom_id))
    rows = q.order_by(QuizSet.created_at.desc()).all()

    return [
        {
            "assessment_id": r[0].id,
            "classroom_id": int(r[1]),
            "title": r[0].topic,
            "level": r[0].level,
            "kind": _normalize_assessment_kind(r[0].kind),
            "created_at": r[0].created_at.isoformat(),
        }
        for r in rows
    ]





def list_assessments_by_type(
    db: Session,
    *,
    user_id: int,
    kind: str,
) -> List[Dict[str, Any]]:
    normalized_kind = _normalize_assessment_kind(kind)
    return [
        item
        for item in list_assessments_for_user(db, user_id=int(user_id))
        if _normalize_assessment_kind(item.get("kind")) == normalized_kind
    ]


def leaderboard_for_assessment(db: Session, *, assessment_id: int) -> Dict[str, Any]:
    quiz_set = db.query(QuizSet).filter(QuizSet.id == assessment_id).first()
    if not quiz_set or (not _is_assessment_kind(quiz_set.kind)):
        raise ValueError("Assessment not found")

    # Latest attempt per user
    from sqlalchemy import and_, func

    sub = (
        db.query(Attempt.user_id, func.max(Attempt.created_at).label("max_created"))
        .filter(Attempt.quiz_set_id == assessment_id)
        .group_by(Attempt.user_id)
        .subquery()
    )

    latest = (
        db.query(Attempt)
        .join(sub, and_(Attempt.user_id == sub.c.user_id, Attempt.created_at == sub.c.max_created))
        .order_by(Attempt.score_percent.desc(), Attempt.created_at.desc())
        .all()
    )

    def _status(a: Attempt) -> str:
        bd = list(a.breakdown_json or [])
        pending = any((i.get("type") == "essay" and not i.get("graded")) for i in bd)
        return "submitted (essay pending)" if pending else "graded"

    return {
        "assessment_id": assessment_id,
        "title": quiz_set.topic,
        "leaderboard": [
            {
                "student_id": a.user_id,
                "attempt_id": a.id,
                "score_percent": int(a.score_percent),
                "status": _status(a),
                "created_at": a.created_at.isoformat() if isinstance(a.created_at, datetime) else str(a.created_at),
            }
            for a in latest
        ],
    }


def grade_essays(
    db: Session,
    *,
    assessment_id: int,
    student_id: int,
    grades: List[Dict[str, Any]],
) -> Dict[str, Any]:
    quiz_set = db.query(QuizSet).filter(QuizSet.id == assessment_id).first()
    if not quiz_set or (not _is_assessment_kind(quiz_set.kind)):
        raise ValueError("Assessment not found")

    attempt = (
        db.query(Attempt)
        .filter(Attempt.quiz_set_id == assessment_id, Attempt.user_id == student_id)
        .order_by(Attempt.created_at.desc())
        .first()
    )
    if not attempt:
        raise ValueError("No submission found for this student")

    breakdown = copy.deepcopy(attempt.breakdown_json or [])
    grade_map = {int(g.get("question_id")): g for g in (grades or [])}

    for item in breakdown:
        if item.get("type") != "essay":
            continue
        qid = int(item.get("question_id"))
        if qid not in grade_map:
            continue
        g = grade_map[qid]
        score_points = int(g.get("score_points", 0))
        max_points = int(item.get("max_points", 10))
        if score_points < 0:
            score_points = 0
        if score_points > max_points:
            score_points = max_points
        item["score_points"] = score_points
        item["comment"] = g.get("comment")
        item["graded"] = True

    # Recompute score using 70/30 (MCQ/Eassy)
    pending = any((i.get("type") == "essay" and not i.get("graded")) for i in breakdown)

    split = _split_scores_from_breakdown(breakdown)
    mcq_percent = int(split["mcq_percent"])
    essay_percent = int(split["essay_percent"])
    score_percent = int(split["total_percent"])

    # Level gate only for diagnostic kinds
    gate = (quiz_set.kind or '').lower() in ("diagnostic_pre", "diagnostic_post")
    computed_level = _level_from_total(score_percent, essay_percent=essay_percent, gate_essay=gate)
    # Point totals for info
    earned_points = int(split["mcq_earned"]) + int(split["essay_earned"])
    total_points = int(split["mcq_total"]) + int(split["essay_total"])

    attempt.breakdown_json = breakdown
    flag_modified(attempt, "breakdown_json")
    attempt.score_percent = score_percent
    db.commit()
    db.refresh(attempt)

    synced = sync_diagnostic_from_attempt(db, quiz_set=quiz_set, attempt=attempt)

    return {
        "assessment_id": assessment_id,
        "attempt_id": attempt.id,
        "student_id": student_id,
        "score_percent": score_percent,
        "mcq_score_percent": mcq_percent,
        "essay_score_percent": essay_percent,
        "total_score_percent": score_percent,
        "computed_level": computed_level,
        "score_points": earned_points,
        "max_points": total_points,
        "status": "graded" if not pending else "partially graded",
        "breakdown": breakdown,
        "synced_diagnostic": synced,
    }



def get_latest_submission(db: Session, *, assessment_id: int, student_id: int) -> Dict[str, Any]:
    """Teacher helper: fetch the latest submission (Attempt) + enriched breakdown."""
    quiz_set = db.query(QuizSet).filter(QuizSet.id == assessment_id).first()
    if not quiz_set or (not _is_assessment_kind(quiz_set.kind)):
        raise ValueError("Assessment not found")

    attempt = (
        db.query(Attempt)
        .filter(Attempt.quiz_set_id == assessment_id, Attempt.user_id == student_id)
        .order_by(Attempt.created_at.desc())
        .first()
    )
    if not attempt:
        raise ValueError("No submission found for this student")

    questions = (
        db.query(Question)
        .filter(Question.quiz_set_id == assessment_id)
        .order_by(Question.order_no.asc())
        .all()
    )
    qmap = {q.id: q for q in questions}

    breakdown = copy.deepcopy(attempt.breakdown_json or [])

    # Enrich breakdown with question stem / rubric (useful for teacher UI)
    for item in breakdown:
        qid = int(item.get("question_id"))
        q = qmap.get(qid)
        if not q:
            continue
        item.setdefault("stem", q.stem)
        if q.type == "essay":
            item.setdefault("rubric", q.rubric or [])
            item.setdefault("max_points", int(q.max_points or 10))
        else:
            item.setdefault("options", q.options or [])
            item.setdefault("max_points", 1)
            item.setdefault("explanation", q.explanation)

    # Determine grading status
    pending = any((i.get("type") == "essay" and not i.get("graded")) for i in breakdown)
    status = "submitted (essay pending)" if pending else "graded"

    # Compute split scores (70/30) + points (for display)
    split = _split_scores_from_breakdown(breakdown)
    total_points = int(split['mcq_total']) + int(split['essay_total'])
    earned_points = int(split['mcq_earned']) + int(split['essay_earned'])

    gate = (quiz_set.kind or '').lower() in ('diagnostic_pre', 'diagnostic_post')
    computed_level = _level_from_total(int(split['total_percent']), essay_percent=int(split['essay_percent']), gate_essay=gate)

    return {
        'assessment_id': assessment_id,
        'title': quiz_set.topic,
        'student_id': student_id,
        'attempt_id': attempt.id,
        'created_at': attempt.created_at.isoformat() if isinstance(attempt.created_at, datetime) else str(attempt.created_at),
        'score_percent': int(attempt.score_percent),
        'mcq_score_percent': int(split['mcq_percent']),
        'essay_score_percent': int(split['essay_percent']),
        'total_score_percent': int(split['total_percent']),
        'computed_level': computed_level,
        'score_points': earned_points,
        'max_points': total_points,
        'status': status,
        'breakdown': breakdown,
    }



def sync_diagnostic_from_attempt(db: Session, *, quiz_set: QuizSet, attempt: Attempt) -> Optional[Dict[str, Any]]:
    """If quiz_set.kind is diagnostic_pre/post and attempt is fully graded, write diagnostic_attempts + update learner_profile."""
    kind = (quiz_set.kind or "").lower()
    if kind not in ("diagnostic_pre", "diagnostic_post"):
        return None

    breakdown = list(attempt.breakdown_json or [])
    pending = any((i.get("type") == "essay" and not i.get("graded")) for i in breakdown)

    split = _split_scores_from_breakdown(breakdown)
    mcq_percent = int(split["mcq_percent"])
    essay_percent = int(split["essay_percent"])
    total_percent = int(split["total_percent"])

    gate = True
    if pending:
        gate = False

    level = _level_from_total(total_percent, essay_percent=essay_percent, gate_essay=gate)

    # Teacher topic (assessment title) is still stored for UI context,
    # but we ALSO keep per-topic mastery (inferred from each question's stem/topic)
    # so Learning Path can be more personalized.
    teacher_topic = (quiz_set.topic or "").strip() or "chủ đề"

    mastery_by_topic = _topic_mastery_from_breakdown(breakdown)
    # Ensure we always have at least 1 entry.
    if not mastery_by_topic:
        mastery_by_topic = {teacher_topic.lower(): float(total_percent) / 100.0}

    # Weak topics = mastery < 0.6 (cap for UI)
    weak_topics = [t for t, v in (mastery_by_topic or {}).items() if float(v) < 0.6]
    weak_topics = weak_topics[:8]

    stage = "pre" if kind == "diagnostic_pre" else "post"

    # Upsert learner profile
    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == attempt.user_id).first()
    if not profile:
        profile = LearnerProfile(user_id=attempt.user_id, level=level, mastery_json={})
        db.add(profile)
        db.flush()

    # Merge mastery
    merged = dict(profile.mastery_json or {})
    for t, v in mastery_by_topic.items():
        merged[t] = float(v)
    merged["overall"] = float(total_percent) / 100.0
    if stage == "post":
        merged["overall_post"] = float(total_percent) / 100.0
    profile.mastery_json = merged

    # Update level only for pre-test
    if stage == "pre":
        profile.level = level

    # Upsert diagnostic_attempt
    existing = (
        db.query(DiagnosticAttempt)
        .filter(DiagnosticAttempt.user_id == attempt.user_id, DiagnosticAttempt.assessment_id == quiz_set.id)
        .first()
    )
    # Preserve any previous auto-assigned plan id (avoid generating multiple plans for the same diagnostic).
    prev_plan_id = None
    if existing and isinstance(existing.mastery_json, dict):
        prev_plan_id = (existing.mastery_json or {}).get("plan_id")

    payload = dict(
        user_id=attempt.user_id,
        stage=stage,
        assessment_id=quiz_set.id,
        attempt_id=attempt.id,
        score_percent=total_percent,
        mcq_score_percent=mcq_percent,
        essay_score_percent=essay_percent,
        correct_count=int(split["mcq_earned"]),
        total=int(split["mcq_total"]),
        level=level,
        answers_json=list(attempt.answers_json or []),
        mastery_json={
            "teacher_topic": teacher_topic,
            "by_topic": mastery_by_topic,
            "weak_topics": weak_topics,
            "mcq_percent": mcq_percent,
            "essay_percent": essay_percent,
            "total_percent": total_percent,
            "pending": bool(pending),
            **({"plan_id": prev_plan_id} if prev_plan_id else {}),
        },
    )

    diag_row: DiagnosticAttempt
    if existing:
        for k, v in payload.items():
            setattr(existing, k, v)
        diag_row = existing
    else:
        diag_row = DiagnosticAttempt(**payload)
        db.add(diag_row)

    db.commit()
    db.refresh(diag_row)

    # -------------------------
    # Auto-assign learning plan right after PRE diagnostic (placement test)
    # -------------------------
    plan_id: int | None = None
    classroom_id: int | None = None
    try:
        mj = diag_row.mastery_json or {}
        if isinstance(mj, dict):
            pid = mj.get("plan_id")
            plan_id = int(pid) if pid is not None else None
    except Exception:
        plan_id = None

    if stage == "pre":
        try:
            from app.models.learning_plan import LearningPlan
            from app.services.learning_plan_service import build_teacher_learning_plan
            from app.services.learning_plan_storage_service import save_teacher_plan

            # Find classroom context (first mapping).
            try:
                row = (
                    db.query(ClassroomAssessment.classroom_id)
                    .filter(ClassroomAssessment.assessment_id == int(quiz_set.id))
                    .limit(1)
                    .first()
                )
                if row and row[0] is not None:
                    classroom_id = int(row[0])
            except Exception:
                classroom_id = None

            # If we already have a plan id and it exists, don't generate again.
            if plan_id is not None:
                exists_plan = db.query(LearningPlan.id).filter(LearningPlan.id == int(plan_id)).first()
                if exists_plan:
                    # keep
                    pass
                else:
                    plan_id = None

            if plan_id is None:
                days_total = int(getattr(settings, "LEARNING_PLAN_DAYS", 7) or 7)
                minutes_per_day = int(getattr(settings, "LEARNING_PLAN_MINUTES_PER_DAY", 35) or 35)

                teacher_plan = build_teacher_learning_plan(
                    db,
                    user_id=int(attempt.user_id),
                    teacher_id=int(getattr(quiz_set, "user_id", 1) or 1),
                    level=str(level or "beginner"),
                    assigned_topic=teacher_topic,
                    modules=[],
                    days=days_total,
                    minutes_per_day=minutes_per_day,
                )

                plan_row = save_teacher_plan(
                    db,
                    user_id=int(attempt.user_id),
                    teacher_id=int(getattr(quiz_set, "user_id", 1) or 1),
                    classroom_id=classroom_id,
                    assigned_topic=teacher_topic,
                    level=str(level or "beginner"),
                    days_total=int(teacher_plan.days_total or days_total),
                    minutes_per_day=int(teacher_plan.minutes_per_day or minutes_per_day),
                    teacher_plan=teacher_plan.model_dump(),
                )
                plan_id = int(plan_row.id)

                # Store the plan id back to diagnostic_attempt for idempotency.
                mj2 = dict(diag_row.mastery_json or {})
                mj2["plan_id"] = int(plan_id)
                diag_row.mastery_json = mj2

                from app.services.notification_service import create_notification

                create_notification(
                    db,
                    user_id=int(attempt.user_id),
                    type="learning_plan_ready",
                    title="Lộ trình học mới đã sẵn sàng!",
                    message=f"AI đã tạo lộ trình học phù hợp với trình độ {level} của bạn. Click để xem!",
                    data={
                        "learning_plan_id": int(plan_id),
                        "level": str(level or "beginner"),
                        "topic": str(teacher_topic),
                    },
                )
                db.commit()
        except Exception:
            # Do not fail the submission if auto-plan generation fails.
            pass

    return {
        "stage": stage,
        "level": level,
        "mcq_score_percent": mcq_percent,
        "essay_score_percent": essay_percent,
        "total_score_percent": total_percent,
        "weak_topics": weak_topics,
        "teacher_topic": teacher_topic,
        "plan_id": plan_id,
        "classroom_id": classroom_id,
    }
