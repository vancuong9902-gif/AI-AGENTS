from __future__ import annotations

import json
import math
import re
import hashlib
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_topic import DocumentTopic
from app.models.quiz_set import QuizSet
from app.models.question import Question
from app.models.attempt import Attempt
from app.models.diagnostic_attempt import DiagnosticAttempt
from app.models.learner_profile import LearnerProfile
from app.models.classroom import Classroom
from app.services.user_service import ensure_user_exists
from app.services.corrective_rag import corrective_retrieve_and_log
from app.services.rag_service import auto_document_ids_for_query
from app.services.text_quality import filter_chunks_by_quality
from app.services.llm_service import llm_available, chat_json, pack_chunks
from app.services.learner_modeling_service import update_mastery_from_breakdown
from app.services.retention_scheduler import create_retention_schedules

from app.services.topic_service import (
    build_topic_details,
    enrich_topic_details_with_llm,
    clean_topic_text_for_display,
    split_study_and_practice,
)


# ------------------------------
# Phase 1: Document Analysis
# ------------------------------


def _short_doc_summary(text: str) -> str:
    t = " ".join((text or "").split())
    if not t:
        return ""
    if len(t) <= 800:
        return t
    return t[:799].rstrip() + "…"


def _llm_doc_summary(text: str, title: str = "") -> str:
    if not llm_available():
        return _short_doc_summary(text)
    clean = "\n".join((text or "").splitlines()[:240]).strip()[:9000]
    sys = (
        "Bạn là giáo viên. Hãy tóm tắt tài liệu một cách học được (không bịa). "
        "Trả về 5-8 gạch đầu dòng, mỗi gạch 1 câu ngắn."
    )
    user = {"title": title, "excerpt": clean, "output": {"bullets": ["string"]}}
    try:
        obj = chat_json(
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=420,
        )
        bullets = obj.get("bullets") if isinstance(obj, dict) else None
        if isinstance(bullets, list):
            out = ["- " + str(x).strip() for x in bullets if str(x).strip()]
            if out:
                return "\n".join(out)[:1800]
    except Exception:
        pass
    return _short_doc_summary(text)


def build_phase1_document_analysis(
    db: Session,
    *,
    document_id: int,
    include_llm: bool = True,
    max_topics: int = 40,
) -> Dict[str, Any]:
    doc = db.query(Document).filter(Document.id == int(document_id)).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    topics = (
        db.query(DocumentTopic)
        .filter(DocumentTopic.document_id == int(document_id))
        .order_by(DocumentTopic.topic_index.asc())
        .all()
    )
    topics = topics[: max(1, int(max_topics))]

    doc_summary = _llm_doc_summary(doc.content or "", title=str(doc.title or "")) if include_llm else _short_doc_summary(doc.content or "")

    out_topics: List[Dict[str, Any]] = []
    for t in topics:
        if t.start_chunk_index is None or t.end_chunk_index is None:
            continue
        chs = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == int(document_id))
            .filter(DocumentChunk.chunk_index >= int(t.start_chunk_index))
            .filter(DocumentChunk.chunk_index <= int(t.end_chunk_index))
            .order_by(DocumentChunk.chunk_index.asc())
            .all()
        )
        body_raw = "\n\n".join([c.text or "" for c in chs]).strip()
        body_view = clean_topic_text_for_display(body_raw)
        study_view, _practice_view = split_study_and_practice(body_view)
        study_view = study_view or body_view

        base = build_topic_details(study_view, title=str(t.title or ""))
        llm_det: Dict[str, Any] = {}
        if include_llm:
            try:
                llm_det = enrich_topic_details_with_llm(study_view, title=str(t.title or "")) or {}
            except Exception:
                llm_det = {}

        # Map to Phase-1-required fields (with safe fallbacks).
        learning_objectives = llm_det.get("learning_objectives") or llm_det.get("objectives") or []
        if not isinstance(learning_objectives, list):
            learning_objectives = []
        core_concepts = llm_det.get("core_concepts") or llm_det.get("core_concept") or llm_det.get("key_points") or base.get("key_points") or []
        if not isinstance(core_concepts, list):
            core_concepts = []

        key_definitions = llm_det.get("key_definitions") or llm_det.get("definitions") or base.get("definitions") or []
        if not isinstance(key_definitions, list):
            key_definitions = []

        important_formulas = llm_det.get("important_formulas") or llm_det.get("formulas") or base.get("formulas") or []
        if not isinstance(important_formulas, list):
            important_formulas = []

        worked_examples = llm_det.get("worked_examples") or llm_det.get("examples") or base.get("examples") or []
        if not isinstance(worked_examples, list):
            worked_examples = []

        common_mistakes = llm_det.get("common_mistakes") or llm_det.get("misconceptions") or []
        if not isinstance(common_mistakes, list):
            common_mistakes = []

        practical_applications = llm_det.get("practical_applications") or llm_det.get("applications") or []
        if not isinstance(practical_applications, list):
            practical_applications = []

        out_topics.append(
            {
                "topic_id": int(t.id),
                "topic_index": int(t.topic_index or 0),
                "title": str(t.title or ""),
                "learning_objectives": [" ".join(str(x).split())[:220] for x in learning_objectives if str(x).strip()][:10],
                "core_concepts": [" ".join(str(x).split())[:320] for x in core_concepts if str(x).strip()][:16],
                "key_definitions": key_definitions[:14],
                "important_formulas": [" ".join(str(x).split())[:220] for x in important_formulas if str(x).strip()][:10],
                "worked_examples": [str(x).strip()[:600] for x in worked_examples if str(x).strip()][:10],
                "common_mistakes": [" ".join(str(x).split())[:320] for x in common_mistakes if str(x).strip()][:10],
                "practical_applications": [" ".join(str(x).split())[:320] for x in practical_applications if str(x).strip()][:10],
                "summary": str(llm_det.get("summary") or t.summary or "").strip()[:420] or None,
                "keywords": (llm_det.get("keywords") if isinstance(llm_det.get("keywords"), list) else (t.keywords or []))[:14],
                "outline": (llm_det.get("outline") if isinstance(llm_det.get("outline"), list) else base.get("outline") or [])[:18],
                "study_guide_md": (llm_det.get("study_guide_md") or base.get("study_guide_md") or None),
                "self_check": (llm_det.get("self_check") if isinstance(llm_det.get("self_check"), list) else [])[:10],
                "content_preview": " ".join(study_view.split())[:1200] if study_view else None,
            }
        )

    return {
        "document_id": int(doc.id),
        "title": str(doc.title or ""),
        "doc_summary": doc_summary,
        "topics": out_topics,
    }


# ------------------------------
# Entry Test / Final Exam
# ------------------------------


_QTYPE_TO_INTERNAL = {
    "mcq": "mcq",
    "short_answer": "short",
    "application": "application",
    "analytical": "analytical",
    "complex": "complex",
}

_INTERNAL_TO_QTYPE = {
    "mcq": "mcq",
    "short": "short_answer",
    "application": "application",
    "analytical": "analytical",
    "complex": "complex",
}


def _normalize_stem_for_fingerprint(stem: str) -> str:
    text = re.sub(r"[^\w\sÀ-ỹ]", " ", str(stem or "").lower(), flags=re.UNICODE)
    return " ".join(text.split())


def _stem_fingerprint(stem: str) -> str:
    normalized = _normalize_stem_for_fingerprint(stem)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def generate_diagnostic_pre_payload(
    *,
    selected_topics: List[str],
    evidence_chunks: List[Dict[str, Any]],
    config: Dict[str, Any],
    time_policy: str,
    duration_seconds: int,
    exclude_history: Optional[List[str]] = None,
    excluded_questions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Generate a strict diagnostic_pre payload for Assessment Agent contract."""
    topics = [str(t).strip() for t in (selected_topics or []) if str(t).strip()]
    if not topics:
        raise HTTPException(status_code=422, detail="selected_topics is required")
    if not evidence_chunks:
        raise HTTPException(status_code=422, detail="evidence_chunks is required")

    easy_count = int(config.get("easy_count") or 0)
    medium_count = int(config.get("medium_count") or 0)
    hard_count = int(config.get("hard_count") or 0)
    target_by_difficulty = {"easy": easy_count, "medium": medium_count, "hard": hard_count}
    total_needed = easy_count + medium_count + hard_count
    if total_needed <= 0:
        raise HTTPException(status_code=422, detail="config question counts must be > 0")

    valid_chunk_ids = {int(c.get("chunk_id")) for c in evidence_chunks if c.get("chunk_id") is not None}
    valid_chunk_ids.discard(None)
    if not valid_chunk_ids:
        raise HTTPException(status_code=422, detail="evidence_chunks must include chunk_id")

    lang = "Vietnamese"
    blocked = {str(x).strip() for x in (exclude_history or []) if str(x).strip()}
    blocked.update({str(x).strip() for x in (excluded_questions or []) if str(x).strip()})
    collected: List[Dict[str, Any]] = []

    for _ in range(3):
        prompts_blocked = sorted(list(blocked | {q["fingerprint"] for q in collected}))[:150]
        sys = (
            "Bạn là giáo viên ra đề. CHỈ dùng evidence_chunks. "
            "Sinh đề theo 3 độ khó: easy (remember/understand), medium (apply/analyze), "
            "hard (evaluate/create). "
            "Phải phủ đều topics giáo viên chọn; mỗi câu có sources (chunk_id). "
            "Không trùng ý/câu chữ với excluded_questions. "
            "Trả về JSON hợp lệ duy nhất, có đáp án và giải thích ngắn; essay phải có rubric chấm. "
            "Nếu evidence không đủ thì giảm số câu hoặc trả lỗi có hướng dẫn, tuyệt đối không bịa."
        )
        user = {
            "selected_topics": topics,
            "evidence_chunks": evidence_chunks,
            "excluded_questions": prompts_blocked,
            "config": {
                "easy_count": easy_count,
                "medium_count": medium_count,
                "hard_count": hard_count,
            },
            "time_policy": time_policy,
            "duration_seconds": int(duration_seconds),
            "exclude_history": prompts_blocked,
            "requirements": [
                "100% câu hỏi phải map topic thuộc selected_topics.",
                "Coverage: phân bổ đều topics; topic nào cũng phải có ít nhất 1 câu khi tổng số câu cho phép.",
                "Mỗi câu có type, stem, explanation, bloom_level, difficulty, topic, sources, estimated_minutes.",
                "Hard nên có 1-2 essay nếu evidence đủ.",
                "estimated_minutes trong [1..6].",
                "sources: ít nhất 1 chunk_id có trong evidence_chunks.",
                "difficulty mapping bắt buộc: easy→remember/understand; medium→apply/analyze; hard→evaluate/create.",
                "Với mcq: options + correct_index; với essay: expected_answer + rubric.",
                "Nếu evidence không đủ thì có thể trả JSON lỗi kèm reason + suggestion; không bịa.",
            ],
            "output_format": {
                "questions": [
                    {
                        "type": "mcq",
                        "stem": "...",
                        "options": ["A", "B", "C", "D"],
                        "correct_index": 0,
                        "explanation": "...",
                        "bloom_level": "remember",
                        "difficulty": "easy",
                        "topic": topics[0],
                        "sources": [{"chunk_id": int(next(iter(valid_chunk_ids)))}],
                        "estimated_minutes": 2,
                    }
                ]
            },
            "language": lang,
        }

        obj = chat_json(
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=2600,
        )
        if isinstance(obj, dict) and str(obj.get("status") or "").upper() in {"ERROR", "NEED_MORE_EVIDENCE", "NEED_CLEAN_TEXT"}:
            continue

        raw = obj.get("questions") if isinstance(obj, dict) else None
        if not isinstance(raw, list):
            continue

        for q in raw:
            if not isinstance(q, dict):
                continue
            difficulty = str(q.get("difficulty") or "").strip().lower()
            if difficulty not in target_by_difficulty:
                continue
            if len([x for x in collected if x.get("difficulty") == difficulty]) >= target_by_difficulty[difficulty]:
                continue

            qtype = str(q.get("type") or "").strip().lower()
            if qtype not in {"mcq", "essay"}:
                continue

            topic = str(q.get("topic") or "").strip()
            if topic not in topics:
                continue

            stem = " ".join(str(q.get("stem") or "").split()).strip()
            if len(stem) < 8:
                continue
            fp = _stem_fingerprint(stem)
            if fp in blocked or any(fp == it.get("fingerprint") for it in collected):
                continue

            sources = q.get("sources")
            if isinstance(sources, dict):
                sources = [sources]
            cleaned_sources: List[Dict[str, int]] = []
            if isinstance(sources, list):
                for it in sources:
                    cid = (it.get("chunk_id") if isinstance(it, dict) else it)
                    try:
                        cid_i = int(cid)
                    except Exception:
                        continue
                    if cid_i in valid_chunk_ids:
                        src = {"chunk_id": cid_i}
                        if isinstance(it, dict) and it.get("page") is not None:
                            try:
                                src["page"] = int(it.get("page"))
                            except Exception:
                                pass
                        cleaned_sources.append(src)
            if not cleaned_sources:
                continue

            try:
                est = int(q.get("estimated_minutes") or 0)
            except Exception:
                est = 0
            if est <= 0:
                est = {"easy": 2, "medium": 3, "hard": 5}.get(difficulty, 2)
            est = max(1, min(6, est))

            item: Dict[str, Any] = {
                "type": qtype,
                "stem": stem,
                "explanation": " ".join(str(q.get("explanation") or "").split()).strip(),
                "bloom_level": str(q.get("bloom_level") or "understand").strip().lower(),
                "difficulty": difficulty,
                "topic": topic,
                "sources": cleaned_sources[:2],
                "estimated_minutes": est,
                "fingerprint": fp,
            }

            bloom = str(item.get("bloom_level") or "").strip().lower()
            allowed_by_difficulty = {
                "easy": {"remember", "understand"},
                "medium": {"apply", "analyze"},
                "hard": {"evaluate", "create"},
            }
            if bloom not in allowed_by_difficulty.get(difficulty, set()):
                continue

            if qtype == "mcq":
                options = q.get("options") if isinstance(q.get("options"), list) else []
                options = [" ".join(str(o).split()).strip() for o in options if str(o).strip()]
                if len(options) != 4:
                    continue
                try:
                    correct_index = int(q.get("correct_index"))
                except Exception:
                    continue
                if correct_index not in (0, 1, 2, 3):
                    continue
                item.update({"options": options, "correct_index": correct_index})
            else:
                expected_answer = " ".join(str(q.get("expected_answer") or "").split()).strip()
                rubric = q.get("rubric") if isinstance(q.get("rubric"), list) else []
                if not expected_answer or not rubric:
                    continue
                item.update({"expected_answer": expected_answer, "rubric": rubric})

            collected.append(item)

        done = all(len([x for x in collected if x.get("difficulty") == d]) >= c for d, c in target_by_difficulty.items())
        if done:
            break

    counts = Counter(str(q.get("difficulty")) for q in collected)
    if any(int(counts.get(d, 0)) < int(c) for d, c in target_by_difficulty.items()):
        raise HTTPException(status_code=422, detail="Unable to generate enough unique questions matching constraints")

    questions: List[Dict[str, Any]] = []
    for d in ("easy", "medium", "hard"):
        need = target_by_difficulty[d]
        picked = [q for q in collected if q.get("difficulty") == d][:need]
        questions.extend(picked)

    if hard_count > 0:
        hard_essays = [q for q in questions if q.get("difficulty") == "hard" and q.get("type") == "essay"]
        if not hard_essays:
            raise HTTPException(status_code=422, detail="Hard section requires essay evidence but none generated")

    if len(topics) <= len(questions):
        covered_topics = {str(q.get("topic") or "").strip() for q in questions}
        if any(t not in covered_topics for t in topics):
            raise HTTPException(status_code=422, detail="Unable to satisfy balanced topic coverage")

    total_estimated = sum(int(q.get("estimated_minutes") or 0) for q in questions)
    limit_from_estimate = int(math.ceil(total_estimated * 1.1))
    limit_from_duration = int(math.ceil(int(duration_seconds) / 60.0))
    time_limit_minutes = min(limit_from_estimate, limit_from_duration)

    topic_title = ", ".join(topics[:3])
    return {
        "title": f"Bài kiểm tra đầu vào - {topic_title}",
        "kind": "diagnostic_pre",
        "time_limit_minutes": int(time_limit_minutes),
        "questions": questions,
    }


def _build_exam_retrieval_context(
    db: Session,
    *,
    document_ids: List[int],
    topics: List[str],
    rag_query: Optional[str],
    top_k: int,
) -> Dict[str, Any]:
    # Auto-scope like tutor: default to teacher docs
    doc_ids = list(document_ids or [])
    if not doc_ids:
        auto = auto_document_ids_for_query(db, (rag_query or " ".join(topics)).strip() or "tài liệu", preferred_user_id=settings.DEFAULT_TEACHER_ID, max_docs=3)
        if auto:
            doc_ids = auto

    query = (rag_query or "").strip()
    if not query:
        if topics:
            query = " | ".join([t.strip() for t in topics if t.strip()][:8])
        else:
            query = "tổng quan nội dung tài liệu"

    filters = {"document_ids": doc_ids} if doc_ids else {}
    rag = corrective_retrieve_and_log(db=db, query=query, top_k=int(max(8, min(40, top_k))), filters=filters, topic=(topics[0] if topics else None))
    chunks = rag.get("chunks") or []
    good, bad = filter_chunks_by_quality(chunks, min_score=float(settings.OCR_MIN_QUALITY_SCORE))
    bad_ratio = float(len(bad)) / float(max(1, len(chunks)))
    if (not good) or (bad_ratio >= float(settings.OCR_BAD_CHUNK_RATIO) and len(good) < 2):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "NEED_CLEAN_TEXT",
                "message": "CONTEXT bị lỗi OCR / rời rạc nên không thể sinh đề chắc chắn.",
                "reason": f"bad_chunk_ratio={bad_ratio:.2f}, good={len(good)}, total={len(chunks)}",
                "suggestion": "Hãy upload file .docx hoặc PDF có text layer / hoặc copy-paste đúng phần nội dung cần ra đề.",
                "debug": {"sample_bad": bad[:2]},
            },
        )

    packed = pack_chunks(good, max_chunks=min(10, len(good)), max_chars_per_chunk=900, max_total_chars=6200)
    return {"rag": rag.get("corrective") or {}, "packed_chunks": packed, "doc_ids": doc_ids, "query": query}


def _llm_generate_exam_questions(
    *,
    kind: str,
    language: str,
    packed_chunks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Generate exam questions with answer keys in a strict structure.

    Returns list of question dicts:
      {section, qtype, stem, options?, correct_index?, ideal_answer?, explanation, keywords?}
    """
    if not llm_available():
        raise HTTPException(status_code=422, detail="LLM is required to generate exams in this demo")

    if kind == "entry_test":
        spec = {
            "EASY": {"mcq": 5, "short_answer": 2, "application": 1},
            "MEDIUM": {"mcq": 5, "short_answer": 2, "application": 1},
            "HARD": {"mcq": 5, "analytical": 2, "complex": 1},
        }
        title = "Bài kiểm tra đầu vào (3 mức độ)"
    elif kind == "retention_check":
        # Retention checks should be short to reduce learner burden while still probing recall.
        # Keep them in MEDIUM section for simpler downstream handling.
        spec = {
            "EASY": {"mcq": 0},
            "MEDIUM": {"mcq": 4, "short_answer": 1, "application": 1},
            "HARD": {"mcq": 0},
        }
        title = "Bài kiểm tra ghi nhớ (Retention Check)"
    else:
        spec = {
            "EASY": {"mcq": 5, "short_answer": 2},
            "MEDIUM": {"mcq": 8, "short_answer": 3, "application": 2},
            "HARD": {"mcq": 5, "analytical": 3, "complex": 2},
        }
        title = "Bài kiểm tra cuối kỳ tổng hợp (3 mức độ)"

    sys = (
        "Bạn là GIÁO VIÊN ra đề và chấm đáp án mẫu. "
        "CHỈ dùng thông tin có trong evidence_chunks. Không bịa kiến thức ngoài. "
        "Không copy nguyên văn dài. "
        "Trả về JSON hợp lệ theo schema yêu cầu."
    )

    user = {
        "language": language,
        "title": title,
        "requirements": {
            "spec": spec,
            "rules": [
                "MCQ phải có 4 lựa chọn A-D và 1 đáp án đúng.",
                "Short answer / application / analytical / complex phải có: ideal_answer (ngắn gọn) + keywords (3-8 từ khóa) + explanation (vì sao đúng).",
                "Mỗi câu phải gắn sources: 1-2 chunk_id từ evidence_chunks.",
                "Câu hỏi phải rõ ràng, không mơ hồ, không trùng ý.",
            ] + ([
                "QUAN TRỌNG: Đây là bài kiểm tra CUỐI KỲ.",
                "1. KHÔNG trùng với bài kiểm tra đầu vào (câu hỏi gốc đã biết).",
                "2. Ưu tiên Bloom level cao hơn (apply/analyze/evaluate/create thay vì remember/understand).",
                "3. Tập trung vào ứng dụng thực tế, so sánh, phân tích — không hỏi thuần định nghĩa.",
                "4. Ít nhất 40% câu hỏi dạng scenario-based ('Trong tình huống A, nếu B thì C?').",
            ] if kind == "final_exam" else []),
        },
        "evidence_chunks": packed_chunks,
        "output_format": {
            "questions": [
                {
                    "section": "EASY|MEDIUM|HARD",
                    "qtype": "mcq|short_answer|application|analytical|complex",
                    "stem": "string",
                    "options": ["A", "B", "C", "D"],
                    "correct_index": 0,
                    "ideal_answer": "string",
                    "keywords": ["string"],
                    "explanation": "string",
                    "sources": [{"chunk_id": 0}],
                }
            ]
        },
    }

    try:
        obj = chat_json(
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.25,
            max_tokens=2200 if kind == "final_exam" else (900 if kind == "retention_check" else 1900),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM generation failed: {e}")

    qs = obj.get("questions") if isinstance(obj, dict) else None
    if not isinstance(qs, list) or not qs:
        raise HTTPException(status_code=500, detail="LLM returned empty questions")

    cleaned: List[Dict[str, Any]] = []
    seen = set()
    valid_chunk_ids = {int(c.get("chunk_id")) for c in packed_chunks if c.get("chunk_id") is not None}

    def _norm(s: str) -> str:
        return " ".join(str(s or "").split()).strip()

    for q in qs:
        if not isinstance(q, dict):
            continue
        section = str(q.get("section") or "").strip().upper()
        qtype = str(q.get("qtype") or "").strip()
        stem = _norm(q.get("stem"))
        if section not in {"EASY", "MEDIUM", "HARD"}:
            continue
        if qtype not in {"mcq", "short_answer", "application", "analytical", "complex"}:
            continue
        if len(stem) < 12:
            continue
        key = stem.lower()
        if key in seen:
            continue
        seen.add(key)

        # sources
        sraw = q.get("sources")
        if isinstance(sraw, dict):
            sraw = [sraw]
        sources: List[Dict[str, int]] = []
        if isinstance(sraw, list):
            for it in sraw:
                try:
                    cid = int((it.get("chunk_id") if isinstance(it, dict) else it))
                except Exception:
                    continue
                if cid in valid_chunk_ids:
                    sources.append({"chunk_id": cid})
        sources = sources[:2] if sources else ([{"chunk_id": next(iter(valid_chunk_ids))}] if valid_chunk_ids else [])

        item: Dict[str, Any] = {
            "section": section,
            "qtype": qtype,
            "stem": stem,
            "explanation": _norm(q.get("explanation"))[:1200] or None,
            "sources": sources,
        }

        if qtype == "mcq":
            opts = q.get("options") if isinstance(q.get("options"), list) else []
            opts = [_norm(x) for x in opts if _norm(x)]
            if len(opts) != 4:
                continue
            try:
                ci = int(q.get("correct_index"))
            except Exception:
                ci = -1
            if ci not in (0, 1, 2, 3):
                continue
            item.update({"options": opts, "correct_index": ci})
        else:
            ideal = _norm(q.get("ideal_answer"))
            if len(ideal) < 4:
                continue
            kws = q.get("keywords") if isinstance(q.get("keywords"), list) else []
            kws = [_norm(x).lower() for x in kws if _norm(x)]
            kws = [x for x in kws if len(x) >= 2][:10]
            item.update({"ideal_answer": ideal[:1200], "keywords": kws[:8]})

        cleaned.append(item)

    return cleaned


def _order_questions_for_kind(kind: str, questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    order = {"EASY": 0, "MEDIUM": 1, "HARD": 2}
    qtype_order = {"mcq": 0, "short_answer": 1, "application": 2, "analytical": 3, "complex": 4}
    questions.sort(key=lambda x: (order.get(x.get("section"), 9), qtype_order.get(x.get("qtype"), 9)))
    return questions


def _expected_counts(kind: str) -> Dict[Tuple[str, str], int]:
    if kind == "entry_test":
        return {
            ("EASY", "mcq"): 5,
            ("EASY", "short_answer"): 2,
            ("EASY", "application"): 1,
            ("MEDIUM", "mcq"): 5,
            ("MEDIUM", "short_answer"): 2,
            ("MEDIUM", "application"): 1,
            ("HARD", "mcq"): 5,
            ("HARD", "analytical"): 2,
            ("HARD", "complex"): 1,
        }
    if kind == "retention_check":
        # Lightweight recall probe (MEDIUM section only)
        return {
            ("MEDIUM", "mcq"): 4,
            ("MEDIUM", "short_answer"): 1,
            ("MEDIUM", "application"): 1,
        }
    # final_exam: 3 mức EASY + MEDIUM + HARD, khác cấu trúc entry_test
    return {
        ("EASY", "mcq"): 5,
        ("EASY", "short_answer"): 2,
        ("MEDIUM", "mcq"): 8,
        ("MEDIUM", "short_answer"): 3,
        ("MEDIUM", "application"): 2,
        ("HARD", "mcq"): 5,
        ("HARD", "analytical"): 3,
        ("HARD", "complex"): 2,
    }


def _validate_exam_counts(kind: str, questions: List[Dict[str, Any]]) -> None:
    exp = _expected_counts(kind)
    got: Dict[Tuple[str, str], int] = {}
    for q in questions:
        key = (str(q.get("section")), str(q.get("qtype")))
        got[key] = got.get(key, 0) + 1

    missing = []
    for k, v in exp.items():
        if got.get(k, 0) < v:
            missing.append({"key": k, "expected": v, "got": got.get(k, 0)})

    if missing:
        # We do a best-effort retry with a stricter instruction in the caller.
        raise HTTPException(status_code=500, detail={"message": "LLM did not satisfy required counts", "missing": missing})


def _trim_questions_to_expected(kind: str, questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Trim any extra questions beyond the required spec.

    LLMs occasionally over-generate. For exams we want deterministic sizes
    (especially retention checks). We keep the earliest items after ordering.
    """

    exp = _expected_counts(kind)
    kept: List[Dict[str, Any]] = []
    got: Dict[Tuple[str, str], int] = {}

    for q in questions or []:
        key = (str(q.get("section")), str(q.get("qtype")))
        if key not in exp:
            continue
        cur = got.get(key, 0)
        if cur >= int(exp.get(key, 0)):
            continue
        kept.append(q)
        got[key] = cur + 1

    return kept


def generate_exam(
    db: Session,
    *,
    user_id: int,
    kind: str,
    document_ids: List[int],
    topics: List[str],
    language: str,
    rag_query: Optional[str],
) -> Dict[str, Any]:
    ensure_user_exists(db, int(user_id), role="student")

    top_k = 24 if kind == "entry_test" else (18 if kind == "retention_check" else 30)
    ctx = _build_exam_retrieval_context(db, document_ids=document_ids, topics=topics, rag_query=rag_query, top_k=top_k)

    packed_chunks = ctx["packed_chunks"]

    if kind == "final_exam":
        from app.services import assessment_service

        entry_rows = (
            db.query(DiagnosticAttempt.assessment_id)
            .join(QuizSet, QuizSet.id == DiagnosticAttempt.assessment_id)
            .filter(DiagnosticAttempt.user_id == int(user_id))
            .filter(QuizSet.kind == "entry_test")
            .all()
        )
        excluded_quiz_ids = [int(r[0]) for r in entry_rows if r and r[0] is not None]
        excluded_question_ids: List[int] = []
        if excluded_quiz_ids:
            qrows = db.query(Question.id).filter(Question.quiz_set_id.in_(excluded_quiz_ids)).all()
            excluded_question_ids = [int(r[0]) for r in qrows if r and r[0] is not None]

        seed_payload = {
            "user_id": int(user_id),
            "kind": kind,
            "topics": [str(t).strip().lower() for t in (topics or []) if str(t).strip()],
            "doc_ids": [int(x) for x in (document_ids or [])],
            "excluded_quiz_ids": excluded_quiz_ids,
        }
        generation_seed = hashlib.sha256(json.dumps(seed_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

        classroom = db.query(Classroom).order_by(Classroom.id.asc()).first()
        classroom_id = int(classroom.id) if classroom else 1

        final_assessment = assessment_service.generate_assessment(
            db,
            teacher_id=int(settings.DEFAULT_TEACHER_ID),
            classroom_id=classroom_id,
            title="Final Exam",
            level="intermediate",
            kind="final_exam",
            easy_count=8,
            medium_count=14,
            hard_count=8,
            document_ids=document_ids,
            topics=topics,
            excluded_question_ids=excluded_question_ids,
            dedup_user_id=int(user_id),
            attempt_user_id=int(user_id),
        )
        quiz_id = int(final_assessment.get("assessment_id"))
        qs = db.query(QuizSet).filter(QuizSet.id == quiz_id).first()
        if qs:
            qs.user_id = int(user_id)
            qs.topic = "Final Exam"
            qs.excluded_from_quiz_ids = [int(x) for x in excluded_quiz_ids]
            qs.generation_seed = generation_seed
            db.add(qs)
            db.commit()

        q_out = []
        for idx, q in enumerate((final_assessment.get("questions") or []), start=1):
            qtype = "mcq" if str(q.get("type") or "").lower() == "mcq" else "complex"
            section = "HARD" if str(q.get("type") or "").lower() == "essay" else "MEDIUM"
            q_out.append({
                "question_id": int(q.get("question_id")),
                "order_no": int(idx),
                "section": section,
                "qtype": qtype,
                "stem": str(q.get("stem") or "").strip(),
                "options": list(q.get("options") or []),
            })

        return {
            "quiz_id": quiz_id,
            "kind": kind,
            "title": "Final Exam",
            "questions": q_out,
            "retrieval": ctx.get("rag") or {},
            "deduplication_info": final_assessment.get("deduplication_info") or {"excluded_count": 0, "topics_from_entry": []},
        }

    # LLM generation with one retry if counts mismatch.
    questions: List[Dict[str, Any]] = []
    last_err = None
    for attempt in range(2):
        try:
            questions = _llm_generate_exam_questions(kind=kind, language=language, packed_chunks=packed_chunks)
            questions = _order_questions_for_kind(kind, questions)
            questions = _trim_questions_to_expected(kind, questions)
            _validate_exam_counts(kind, questions)
            break
        except HTTPException as e:
            last_err = e.detail
            if attempt == 0 and llm_available():
                # tighten by re-asking with the missing counts in query (small hack)
                if isinstance(last_err, dict) and last_err.get("missing"):
                    missing = last_err.get("missing")
                    extra = "\n".join([f"- {m['key']}: expected {m['expected']}, got {m['got']}" for m in missing])
                    # prepend extra instruction by adding a synthetic chunk with requirements.
                    packed_chunks = ([{"chunk_id": 999999, "title": "REQ", "text": f"BẮT BUỘC đủ số lượng câu hỏi. Thiếu: {extra}"}] + packed_chunks)[:12]
                    continue
            raise

    if not questions:
        raise HTTPException(status_code=500, detail={"message": "Failed to generate questions", "error": last_err})

    # Persist as QuizSet + Questions
    if kind == "entry_test":
        title = "Entry Test"
    elif kind == "retention_check":
        title = "Retention Check"
    else:
        title = "Final Exam"
    qs = QuizSet(user_id=int(user_id), kind=kind, topic=title, level="mixed", source_query_id=None, excluded_from_quiz_ids=[], generation_seed=None)
    db.add(qs)
    db.flush()

    q_out: List[Dict[str, Any]] = []
    for idx, q in enumerate(questions, start=1):
        qtype = str(q.get("qtype"))
        internal_type = _QTYPE_TO_INTERNAL.get(qtype, qtype)
        section = str(q.get("section") or "MEDIUM")

        bloom = {
            "mcq": "understand",
            "short": "understand",
            "application": "apply",
            "analytical": "analyze",
            "complex": "evaluate",
        }.get(internal_type, "understand")

        opts = q.get("options") if isinstance(q.get("options"), list) else []
        opts = [str(x) for x in opts]

        correct_index = int(q.get("correct_index")) if internal_type == "mcq" else 0
        explanation = (q.get("explanation") or "").strip()[:3000] or None

        rubric: List[Dict[str, Any]] = []
        max_points = 1
        if internal_type != "mcq":
            ideal = str(q.get("ideal_answer") or "").strip()
            kws = q.get("keywords") if isinstance(q.get("keywords"), list) else []
            kws = [str(x).strip().lower() for x in kws if str(x).strip()]
            rubric = [{"ideal_answer": ideal[:1800], "keywords": kws[:10]}]
            # Give slightly more weight for final exam open questions.
            if kind == "final_exam":
                if internal_type == "short":
                    max_points = 2
                else:
                    max_points = 4

        qq = Question(
            quiz_set_id=int(qs.id),
            order_no=int(idx),
            type=internal_type,
            bloom_level=bloom,
            stem=str(q.get("stem") or "").strip(),
            options=opts if internal_type == "mcq" else [],
            correct_index=correct_index,
            explanation=explanation,
            max_points=int(max_points),
            rubric=rubric,
            sources=q.get("sources") if isinstance(q.get("sources"), list) else [],
            estimated_minutes=0,
        )
        # Store section label inside sources meta to avoid DB schema change.
        src = list(qq.sources or [])
        src.append({"meta": {"section": section, "qtype": qtype}})
        qq.sources = src

        db.add(qq)
        db.flush()

        q_out.append(
            {
                "question_id": int(qq.id),
                "order_no": int(qq.order_no),
                "section": section,
                "qtype": qtype,
                "stem": qq.stem,
                "options": list(qq.options or []),
            }
        )

    db.commit()

    return {
        "quiz_id": int(qs.id),
        "kind": kind,
        "title": title,
        "questions": q_out,
        "retrieval": ctx.get("rag") or {},
    }


# ------------------------------
# Grading (MCQ + open ended)
# ------------------------------


def _tokenize(s: str) -> List[str]:
    return [w for w in re.findall(r"[\wÀ-ỹ]+", (s or "").lower()) if len(w) >= 2]


def _keyword_score(answer: str, keywords: List[str]) -> float:
    if not keywords:
        return 0.0
    ans = set(_tokenize(answer))
    keys = set(_tokenize(" ".join(keywords)))
    if not ans or not keys:
        return 0.0
    return len(ans & keys) / float(max(1, len(keys)))


def _llm_grade_open_answer(*, stem: str, ideal: str, keywords: List[str], student_answer: str, max_points: int) -> Tuple[float, str]:
    sys = (
        "Bạn là GIẢNG VIÊN chấm câu trả lời ngắn. "
        "Chỉ dựa trên ideal_answer + keywords đã cho. "
        "Cho điểm theo thang 0..max_points (có thể lẻ 0.5). "
        "Trả JSON: {score_points, feedback}."
    )
    user = {
        "stem": stem,
        "ideal_answer": ideal,
        "keywords": keywords,
        "student_answer": student_answer,
        "max_points": max_points,
    }
    try:
        obj = chat_json(
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.0,
            max_tokens=260,
        )
        if isinstance(obj, dict):
            sp = float(obj.get("score_points", 0.0) or 0.0)
            sp = max(0.0, min(float(max_points), sp))
            fb = str(obj.get("feedback") or "").strip()[:900]
            return sp, fb
    except Exception:
        pass
    return 0.0, ""


def grade_exam(
    db: Session,
    *,
    quiz_id: int,
    user_id: int,
    duration_sec: int,
    answers: List[Dict[str, Any]],
) -> Dict[str, Any]:
    quiz_set = db.query(QuizSet).filter(QuizSet.id == int(quiz_id)).first()
    if not quiz_set:
        raise HTTPException(status_code=404, detail="Quiz not found")

    ensure_user_exists(db, int(user_id), role="student")

    questions: List[Question] = (
        db.query(Question)
        .filter(Question.quiz_set_id == int(quiz_id))
        .order_by(Question.order_no.asc())
        .all()
    )
    if not questions:
        raise HTTPException(status_code=404, detail="Quiz not found")

    # map answer
    a_map: Dict[int, Dict[str, Any]] = {}
    for a in answers or []:
        try:
            qid = int(a.get("question_id"))
        except Exception:
            continue
        a_map[qid] = a

    breakdown: List[Dict[str, Any]] = []
    score_points = 0.0
    max_points = 0.0

    def _meta_section(q: Question) -> str:
        for s in (q.sources or []):
            try:
                meta = (s or {}).get("meta")
                if isinstance(meta, dict) and meta.get("section"):
                    return str(meta.get("section"))
            except Exception:
                continue
        return "MEDIUM"

    def _meta_qtype(q: Question) -> str:
        for s in (q.sources or []):
            try:
                meta = (s or {}).get("meta")
                if isinstance(meta, dict) and meta.get("qtype"):
                    return str(meta.get("qtype"))
            except Exception:
                continue
        # fallback
        return _INTERNAL_TO_QTYPE.get(str(q.type), str(q.type))

    for q in questions:
        section = _meta_section(q)
        qtype = _meta_qtype(q)
        mp = float(getattr(q, "max_points", 1) or 1)
        mp = max(1.0, mp)
        max_points += mp

        chosen = None
        student_text = None
        is_correct = False
        pts = 0.0
        feedback = None

        ans_obj = a_map.get(int(q.id)) or {}

        if str(q.type) == "mcq":
            try:
                chosen = int(ans_obj.get("answer_index"))
            except Exception:
                chosen = -1
            is_correct = chosen == int(q.correct_index)
            pts = mp if is_correct else 0.0
        else:
            student_text = str(ans_obj.get("answer_text") or "").strip()
            rubric = q.rubric or []
            ideal = ""
            keywords: List[str] = []
            if isinstance(rubric, list) and rubric:
                r0 = rubric[0] if isinstance(rubric[0], dict) else {}
                ideal = str(r0.get("ideal_answer") or "").strip()
                keywords = r0.get("keywords") if isinstance(r0.get("keywords"), list) else []
                keywords = [str(x).strip() for x in keywords if str(x).strip()]

            if not student_text:
                pts = 0.0
                feedback = "Bạn chưa trả lời câu này."
            else:
                # heuristic score
                ratio = _keyword_score(student_text, keywords)
                pts = 0.0
                if ratio >= 0.6:
                    pts = mp
                elif ratio >= 0.35:
                    pts = mp * 0.5
                else:
                    pts = 0.0

                if llm_available() and ideal:
                    pts_llm, fb = _llm_grade_open_answer(
                        stem=q.stem,
                        ideal=ideal,
                        keywords=keywords,
                        student_answer=student_text,
                        max_points=int(round(mp)),
                    )
                    # Prefer LLM when it returns a non-empty feedback
                    if fb:
                        pts = float(pts_llm)
                        feedback = fb
                else:
                    if pts >= mp:
                        feedback = "Đúng/đủ ý chính theo từ khóa." if keywords else "Câu trả lời hợp lý." 
                    elif pts > 0:
                        feedback = "Đúng một phần: thiếu một số ý quan trọng." 
                    else:
                        feedback = "Chưa đúng trọng tâm: bạn nên bám vào các từ khóa/ý chính trong tài liệu." 

            is_correct = pts >= (mp * 0.75)

        score_points += float(pts)

        # expose correct/ideal answers
        ideal_answer = None
        correct_index = None
        if str(q.type) == "mcq":
            correct_index = int(q.correct_index)
        else:
            try:
                r0 = (q.rubric or [])[0] if isinstance(q.rubric, list) and q.rubric else {}
                if isinstance(r0, dict):
                    ideal_answer = str(r0.get("ideal_answer") or "").strip()[:1400] or None
            except Exception:
                ideal_answer = None

        breakdown.append(
            {
                "question_id": int(q.id),
                "section": section,
                "qtype": qtype,
                "is_correct": bool(is_correct),
                "score_points": round(float(pts), 3),
                "max_points": round(float(mp), 3),
                "chosen": chosen,
                "student_answer": student_text,
                "correct_index": correct_index,
                "ideal_answer": ideal_answer,
                "explanation": q.explanation,
                "feedback": feedback,
                "sources": q.sources or [],
            }
        )

    score_percent = int(round((score_points / max_points) * 100)) if max_points else 0

    # classification
    if score_percent < 50:
        classification: str = "beginner"
    elif score_percent <= 80:
        classification = "intermediate"
    else:
        classification = "advanced"

    attempt = Attempt(
        quiz_set_id=int(quiz_id),
        user_id=int(user_id),
        score_percent=int(score_percent),
        answers_json=answers,
        breakdown_json=breakdown,
        duration_sec=int(duration_sec or 0),
    )
    db.add(attempt)

    # update profile
    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == int(user_id)).first()
    if not profile:
        profile = LearnerProfile(user_id=int(user_id), level=classification, mastery_json={})
        db.add(profile)
        db.flush()

    profile.level = classification
    mastery = dict(profile.mastery_json or {})
    # Update per-topic mastery posterior (Bayesian Beta update) using evidence-linked questions.
    # This supports adaptive policy state K_t without requiring labeled skill tags.
    try:
        mastery = update_mastery_from_breakdown(db, mastery_json=mastery, breakdown=breakdown)
    except Exception:
        # Never fail grading because learner modeling failed.
        mastery = mastery

    mastery["__last_exam_score_percent__"] = round(float(score_percent) / 100.0, 4)
    mastery["__last_exam_kind__"] = 1.0 if (quiz_set.kind or "") == "final_exam" else 0.0
    profile.mastery_json = mastery

    db.commit()
    db.refresh(attempt)


    # Composite analytics update (FinalScore + dropout prediction).
    # Best-effort: never block grading.
    try:
        from app.services.analytics_service import update_profile_analytics

        update_profile_analytics(
            db,
            user_id=int(user_id),
            document_id=None,
            window_days=14,
            reason=f"attempt:{str(quiz_set.kind or '')}",
        )
    except Exception:
        pass

    # improvement suggestions (simple)
    weak = [b for b in breakdown if not b.get("is_correct")]
    suggestions: List[str] = []
    if weak:
        # group by qtype
        counts: Dict[str, int] = {}
        for b in weak:
            counts[str(b.get("qtype"))] = counts.get(str(b.get("qtype")), 0) + 1
        for qt, c in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:3]:
            if qt == "mcq":
                suggestions.append("Ôn lại khái niệm và định nghĩa cốt lõi (đọc lại phần tóm tắt + key points).")
            elif qt in ("short_answer", "short"):
                suggestions.append("Luyện trả lời ngắn theo cấu trúc: định nghĩa → ý chính → 1 ví dụ.")
            elif qt == "application":
                suggestions.append("Làm thêm bài áp dụng: chọn 1 tình huống và giải từng bước theo quy trình trong tài liệu.")
            elif qt == "analytical":
                suggestions.append("Luyện phân tích: so sánh 2 khái niệm/phương án, nêu tiêu chí và kết luận.")
            elif qt == "complex":
                suggestions.append("Luyện bài tổng hợp: kết nối nhiều ý trong tài liệu để giải một bài toán dài.")

    return {
        "quiz_id": int(quiz_id),
        "attempt_id": int(attempt.id),
        "score_percent": int(score_percent),
        "score_points": round(float(score_points), 3),
        "max_points": round(float(max_points), 3),
        "classification": classification,
        "breakdown": breakdown,
        "improvement_suggestions": suggestions[:6],
    }


def final_exam_analytics(breakdown: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Very light analytics: strengths/weaknesses by bloom + by qtype
    by_qtype: Dict[str, Dict[str, float]] = {}
    for b in breakdown or []:
        qt = str(b.get("qtype") or "")
        by_qtype.setdefault(qt, {"correct": 0.0, "total": 0.0})
        by_qtype[qt]["total"] += float(b.get("max_points", 1.0) or 1.0)
        if bool(b.get("is_correct")):
            by_qtype[qt]["correct"] += float(b.get("score_points", 0.0) or 0.0)
    perf = {k: (int(round((v["correct"] / v["total"]) * 100)) if v["total"] else 0) for k, v in by_qtype.items()}

    # strengths/weaknesses
    strengths = [k for k, p in sorted(perf.items(), key=lambda x: x[1], reverse=True) if p >= 80]
    weak = [k for k, p in sorted(perf.items(), key=lambda x: x[1]) if p <= 60]

    return {
        "by_question_type_percent": perf,
        "strength_areas": strengths[:5],
        "weak_areas": weak[:5],
    }


# ------------------------------
# Phase 4: Topic Mastery Loop
# ------------------------------


def _difficulty_norm(d: str) -> str:
    d = (d or "").strip().lower()
    if d in {"hard", "h"}:
        return "hard"
    if d in {"medium", "m", "mid"}:
        return "medium"
    return "easy"


def _topic_key(document_id: int, topic_id: int, topic_title: str) -> str:
    return f"doc{int(document_id)}:topic{int(topic_id)}:{str(topic_title or '').strip()}".strip(":")


def _llm_topic_recap(*, language: str, packed_chunks: List[Dict[str, Any]], topic_title: str) -> str:
    if not llm_available():
        return ""
    sys = (
        "Bạn là giáo viên. Hãy tóm tắt NHANH phần kiến thức của một chủ đề để học viên ôn lại trước khi làm bài tập. "
        "Chỉ dùng thông tin trong evidence_chunks. Không bịa."
    )
    user = {
        "language": language,
        "topic_title": topic_title,
        "evidence_chunks": packed_chunks,
        "output_format": {
            "recap_md": "string (5-10 bullet points, ngắn gọn, có thể có công thức nếu có)"
        },
    }
    try:
        obj = chat_json(
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=420,
        )
        if isinstance(obj, dict):
            return str(obj.get("recap_md") or "").strip()[:2500]
    except Exception:
        return ""
    return ""


def _llm_generate_topic_exercises(
    *,
    language: str,
    packed_chunks: List[Dict[str, Any]],
    topic_title: str,
    learner_level: str,
    difficulty: str,
) -> List[Dict[str, Any]]:
    if not llm_available():
        raise HTTPException(status_code=422, detail="LLM is required to generate topic exercises")

    learner_level = (learner_level or "beginner").strip().lower()
    difficulty = _difficulty_norm(difficulty)

    # Spec: always 10 exercises; distribution depends on level.
    if learner_level == "advanced":
        spec = {"mcq": 4, "short_answer": 2, "application": 2, "analytical": 2}
    elif learner_level == "intermediate":
        spec = {"mcq": 5, "short_answer": 3, "application": 2}
    else:
        spec = {"mcq": 6, "short_answer": 3, "application": 1}

    sys = (
        "Bạn là GIÁO VIÊN tạo bài tập luyện tập theo chủ đề. "
        "CHỈ dùng thông tin có trong evidence_chunks. Không bịa kiến thức ngoài. "
        "Trả về JSON hợp lệ theo schema yêu cầu."
    )

    user = {
        "language": language,
        "topic_title": topic_title,
        "learner_level": learner_level,
        "difficulty": difficulty,
        "requirements": {
            "count": 10,
            "spec": spec,
            "rules": [
                "MCQ: 4 lựa chọn A-D, 1 đáp án đúng.",
                "Short/application/analytical: có ideal_answer + keywords (3-8 từ) + explanation.",
                "Mỗi câu phải có sources: 1-2 chunk_id từ evidence_chunks.",
                "Câu rõ ràng, không mơ hồ, không trùng ý.",
                "Độ khó phải khớp difficulty (easy/medium/hard).",
            ],
        },
        "evidence_chunks": packed_chunks,
        "output_format": {
            "questions": [
                {
                    "section": "TOPIC",
                    "qtype": "mcq|short_answer|application|analytical",
                    "stem": "string",
                    "options": ["A", "B", "C", "D"],
                    "correct_index": 0,
                    "ideal_answer": "string",
                    "keywords": ["string"],
                    "explanation": "string",
                    "sources": [{"chunk_id": 0}],
                }
            ]
        },
    }

    obj = chat_json(
        messages=[
            {"role": "system", "content": sys},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
        temperature=0.25,
        max_tokens=1800,
    )

    qs = obj.get("questions") if isinstance(obj, dict) else None
    if not isinstance(qs, list) or not qs:
        raise HTTPException(status_code=500, detail="LLM returned no questions")

    # Soft-validate counts (we keep it tolerant to reduce regeneration).
    out: List[Dict[str, Any]] = []
    for q in qs:
        if not isinstance(q, dict):
            continue
        qt = str(q.get("qtype") or "").strip()
        if qt not in {"mcq", "short_answer", "application", "analytical"}:
            continue
        out.append(q)
        if len(out) >= 10:
            break

    if len(out) < 10:
        raise HTTPException(status_code=422, detail={"message": "Insufficient questions", "got": len(out), "expected": 10})

    return out[:10]


def generate_topic_exercises(
    db: Session,
    *,
    user_id: int,
    topic_id: int,
    language: str,
    difficulty: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a 10-item exercise set for a given document topic (Phase 4).

    Returns a quiz payload compatible with grade_exam().
    """

    ensure_user_exists(db, int(user_id), role="student")

    # Learner level (beginner/intermediate/advanced) from profile
    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == int(user_id)).first()
    learner_level = str(profile.level if profile else "beginner")

    topic = db.query(DocumentTopic).filter(DocumentTopic.id == int(topic_id)).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    doc = db.query(Document).filter(Document.id == int(topic.document_id)).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Difficulty default: from profile mastery_json or learner level
    mj = (profile.mastery_json if profile else {}) or {}
    difficulty = _difficulty_norm(difficulty or mj.get("difficulty") or ("medium" if learner_level != "beginner" else "easy"))

    chs = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == int(topic.document_id))
        .filter(DocumentChunk.chunk_index >= int(topic.start_chunk_index or 0))
        .filter(DocumentChunk.chunk_index <= int(topic.end_chunk_index or 0))
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )

    if not chs:
        raise HTTPException(status_code=422, detail="Topic has no chunks")

    # Build chunk dicts for quality filtering + packing.
    chunk_dicts: List[Dict[str, Any]] = []
    for c in chs[:120]:
        chunk_dicts.append(
            {
                "chunk_id": int(c.id),
                "document_id": int(c.document_id),
                "document_title": str(doc.title or ""),
                "chunk_index": int(c.chunk_index),
                "text": c.text or "",
                "meta": c.meta or {},
            }
        )

    good, bad = filter_chunks_by_quality(chunk_dicts, min_score=float(settings.OCR_MIN_QUALITY_SCORE))
    if not good:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "NEED_CLEAN_TEXT",
                "message": "Nội dung chủ đề bị lỗi OCR/rời rạc nên không thể sinh bài tập chắc chắn.",
                "suggestion": "Hãy dùng PDF có text layer hoặc upload DOCX, hoặc chọn một phần ít hơn.",
                "debug": {"bad_samples": bad[:2]},
            },
        )

    packed = pack_chunks(good, max_chunks=min(10, len(good)), max_chars_per_chunk=900, max_total_chars=6200)

    recap_md = _llm_topic_recap(language=language, packed_chunks=packed, topic_title=str(topic.title or ""))

    questions = _llm_generate_topic_exercises(
        language=language,
        packed_chunks=packed,
        topic_title=str(topic.title or ""),
        learner_level=learner_level,
        difficulty=difficulty,
    )

    # Persist quiz set
    qs = QuizSet(
        user_id=int(user_id),
        kind="topic_exercises",
        topic=str(topic.title or ""),
        level=str(difficulty),
        source_query_id=None,
    )
    db.add(qs)
    db.flush()

    q_out: List[Dict[str, Any]] = []
    for idx, q in enumerate(questions, start=1):
        qtype = str(q.get("qtype"))
        internal_type = _QTYPE_TO_INTERNAL.get(qtype, qtype)

        bloom = {
            "mcq": "understand",
            "short": "understand",
            "application": "apply",
            "analytical": "analyze",
        }.get(internal_type, "understand")

        opts = q.get("options") if isinstance(q.get("options"), list) else []
        opts = [str(x) for x in opts]

        correct_index = int(q.get("correct_index")) if internal_type == "mcq" else 0
        explanation = (q.get("explanation") or "").strip()[:3000] or None

        rubric: List[Dict[str, Any]] = []
        max_points = 1
        if internal_type != "mcq":
            ideal = str(q.get("ideal_answer") or "").strip()
            kws = q.get("keywords") if isinstance(q.get("keywords"), list) else []
            kws = [str(x).strip().lower() for x in kws if str(x).strip()]
            rubric = [{"ideal_answer": ideal[:1800], "keywords": kws[:10]}]
            max_points = 2 if internal_type == "short" else 3

        qq = Question(
            quiz_set_id=int(qs.id),
            order_no=int(idx),
            type=internal_type,
            bloom_level=bloom,
            stem=str(q.get("stem") or "").strip(),
            options=opts if internal_type == "mcq" else [],
            correct_index=correct_index,
            explanation=explanation,
            max_points=int(max_points),
            rubric=rubric,
            sources=q.get("sources") if isinstance(q.get("sources"), list) else [],
            estimated_minutes=0,
        )
        src = list(qq.sources or [])
        src.append({"meta": {"section": "TOPIC", "qtype": qtype, "difficulty": difficulty, "topic_id": int(topic.id)}})
        qq.sources = src

        db.add(qq)
        db.flush()

        q_out.append(
            {
                "question_id": int(qq.id),
                "order_no": int(qq.order_no),
                "section": "TOPIC",
                "qtype": qtype,
                "stem": qq.stem,
                "options": list(qq.options or []),
            }
        )

    db.commit()

    return {
        "quiz_id": int(qs.id),
        "kind": "topic_exercises",
        "topic_id": int(topic.id),
        "document_id": int(topic.document_id),
        "topic_title": str(topic.title or ""),
        "topic_key": _topic_key(int(topic.document_id), int(topic.id), str(topic.title or "")),
        "difficulty": difficulty,
        "learner_level": learner_level,
        "recap_md": recap_md or None,
        "questions": q_out,
    }


def postprocess_topic_attempt(
    db: Session,
    *,
    user_id: int,
    topic_id: int,
    quiz_id: int,
    attempt_payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute Phase-4 control logic from a graded attempt.

    Rules (per user spec):
      - if score > 80% => increase difficulty
      - if score < 60% => reinforcement
      - else => continue

    Returns attempt_payload enriched with next_step + next_difficulty + mastery snapshot.
    """

    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == int(user_id)).first()
    mj = (profile.mastery_json if profile else {}) or {}

    topic = db.query(DocumentTopic).filter(DocumentTopic.id == int(topic_id)).first()
    if not topic:
        return {**attempt_payload, "next_step": "continue"}

    tk = _topic_key(int(topic.document_id), int(topic.id), str(topic.title or ""))
    tm = mj.get("topic_mastery", {}) if isinstance(mj.get("topic_mastery"), dict) else {}
    mastery_est = float(tm.get(tk, tm.get("__global__", 0.0)) or 0.0)

    score_percent = int(attempt_payload.get("score_percent") or 0)

    cur_diff = _difficulty_norm(str(mj.get("difficulty") or "easy"))
    diff_i = 0 if cur_diff == "easy" else (1 if cur_diff == "medium" else 2)

    next_step = "continue"
    if score_percent > 80:
        next_step = "increase_difficulty"
        diff_i = min(2, diff_i + 1)
    elif score_percent < 60:
        next_step = "reinforce"
        diff_i = max(0, diff_i - 1)

    next_diff = "easy" if diff_i == 0 else ("medium" if diff_i == 1 else "hard")

    # Automatic spaced-retention scheduling (Delayed Reward hook).
    # If learner demonstrates strong mastery on this topic attempt, schedule short retention checks.
    if score_percent > 80:
        try:
            create_retention_schedules(
                db,
                user_id=int(user_id),
                topic_id=int(topic_id),
                baseline_score_percent=int(score_percent),
                intervals_days=[1, 7, 30],
                source_attempt_id=int(attempt_payload.get("attempt_id")) if attempt_payload.get("attempt_id") else None,
                source_quiz_set_id=int(quiz_id),
            )
        except Exception:
            # Best-effort: never block the mastery loop.
            pass

    # Persist topic progress
    mj.setdefault("topic_progress", {})
    if isinstance(mj.get("topic_progress"), dict):
        mj["topic_progress"][str(topic.id)] = {
            "last_quiz_id": int(quiz_id),
            "last_score_percent": int(score_percent),
            "mastery_estimate": round(float(mastery_est), 4),
            "next_step": next_step,
            "next_difficulty": next_diff,
        }

    mj["difficulty"] = next_diff

    if profile:
        profile.mastery_json = mj
        db.add(profile)
        db.commit()

    return {
        **attempt_payload,
        "topic_id": int(topic.id),
        "document_id": int(topic.document_id),
        "topic_title": str(topic.title or ""),
        "topic_key": tk,
        "topic_score_percent": int(score_percent),
        "mastery_estimate": round(float(mastery_est), 4),
        "next_step": next_step,
        "next_difficulty": next_diff,
    }
