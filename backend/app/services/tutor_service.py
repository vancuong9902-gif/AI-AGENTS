from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.tutor import TutorChatData, TutorGenerateQuestionsData
from app.services.user_service import ensure_user_exists
from app.services.corrective_rag import corrective_retrieve_and_log
from app.services.rag_service import auto_document_ids_for_query
from app.services.text_quality import filter_chunks_by_quality
from app.services.llm_service import llm_available, chat_json, pack_chunks
from app.services.quiz_service import clean_mcq_questions, _generate_mcq_from_chunks
from app.services.topic_service import build_topic_details


def _src_preview(text: str, n: int = 180) -> str:
    s = " ".join(str(text or "").split())
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def tutor_chat(
    db: Session,
    *,
    user_id: int,
    question: str,
    topic: Optional[str] = None,
    top_k: int = 6,
    document_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Virtual AI Tutor (RAG). Answers using only retrieved evidence and suggests follow-ups."""

    ensure_user_exists(db, int(user_id), role="student")

    q = (question or "").strip()
    if not q:
        raise HTTPException(status_code=422, detail="Missing question")

    # Auto-scope to teacher docs by default
    doc_ids = list(document_ids or [])
    if not doc_ids:
        auto = auto_document_ids_for_query(db, topic or q, preferred_user_id=settings.DEFAULT_TEACHER_ID, max_docs=3)
        if auto:
            doc_ids = auto

    filters = {"document_ids": doc_ids} if doc_ids else {}
    query = f"{topic.strip()}: {q}" if topic and topic.strip() else q

    rag = corrective_retrieve_and_log(
        db=db,
        query=query,
        top_k=int(max(3, min(20, top_k))),
        filters=filters,
        topic=topic,
    )

    # If retrieval is clearly irrelevant, politely refuse (user requirement: tutor should not answer off-topic).
    corr = rag.get("corrective") or {}
    attempts = corr.get("attempts") or []
    last_try = attempts[-1] if isinstance(attempts, list) and attempts else {}
    try:
        best_rel = float(last_try.get("best_relevance", 0.0) or 0.0)
    except Exception:
        best_rel = 0.0

    chunks = rag.get("chunks") or []
    # Heuristic: if even the best chunk barely matches the query, we treat it as out-of-scope.
    # (CRAG grading is lexical so we keep the threshold permissive.)
    try:
        import re

        q_words = len(re.findall(r"[\wÀ-ỹ]+", query or ""))
    except Exception:
        q_words = 0
    if chunks and q_words >= 2 and best_rel < float(settings.CRAG_MIN_RELEVANCE) * 0.55:
        answer_md = (
            "Mình chỉ có thể trả lời dựa trên *tài liệu giáo viên đã upload*.\n\n"
            "Câu hỏi này có vẻ **ngoài phạm vi tài liệu hiện tại** (mình không tìm thấy đoạn nào liên quan đủ chắc chắn).\n\n"
            "👉 Gợi ý: hãy chọn đúng *tài liệu* ở dropdown, hoặc nêu rõ *topic/bài* bạn đang học, rồi hỏi lại."
        )
        return TutorChatData(
            answer_md=answer_md,
            follow_up_questions=[
                "Bạn đang học bài/ chương nào trong tài liệu?",
                "Bạn có thể trích 1-2 câu trong tài liệu liên quan để mình giải thích không?",
                "Bạn muốn mình giải thích khái niệm hay làm bài tập theo ví dụ trong tài liệu?",
            ],
            quick_check_mcq=[],
            sources=[],
            retrieval=rag.get("corrective") or {},
        ).model_dump()
    good, bad = filter_chunks_by_quality(chunks, min_score=float(settings.OCR_MIN_QUALITY_SCORE))
    bad_ratio = float(len(bad)) / float(max(1, len(chunks)))
    if (not good) or (bad_ratio >= float(settings.OCR_BAD_CHUNK_RATIO) and len(good) < 2):
        # ChatGPT-like graceful fallback: do NOT hard-error the UI.
        msg = (
            "Mình chưa thể trả lời chắc chắn vì phần tài liệu mình truy xuất được đang bị **lỗi OCR / rời rạc** (chữ bị vỡ, thiếu dấu, sai dòng).\n\n"
            "Bạn có thể làm 1 trong các cách sau để mình trả lời chi tiết hơn:\n"
            "1) Upload lại file **.docx** hoặc PDF có **text layer** (copy được chữ).\n"
            "2) Copy-paste đúng đoạn liên quan (khoảng 10–30 dòng) vào ô chat.\n"
            "3) Nêu rõ *chương/mục* + *từ khoá* để mình lọc đúng phần.\n\n"
            "Nếu bạn gửi lại câu hỏi kèm 1 đoạn trích, mình sẽ giải thích từng bước như giáo viên." 
        )

        return TutorChatData(
            answer_md=msg,
            follow_up_questions=[
                "Bạn đang hỏi trong chương/mục nào của tài liệu?",
                "Bạn có thể dán đoạn văn liên quan (10–30 dòng) không?",
                "Bạn muốn mình giải thích theo kiểu: định nghĩa → ví dụ → lỗi thường gặp hay theo bài tập?",
            ],
            quick_check_mcq=[],
            sources=[],
            retrieval={
                **(rag.get("corrective") or {}),
                "note": "OCR_QUALITY_TOO_LOW",
                "bad_chunk_ratio": bad_ratio,
                "good": len(good),
                "total": len(chunks),
                "sample_bad": bad[:2],
            },
        ).model_dump()
    chunks = good

    # Build sources for UI/debug
    sources = []
    for c in chunks[: min(len(chunks), int(top_k))]:
        sources.append(
            {
                "chunk_id": int(c.get("chunk_id")),
                "document_id": int(c.get("document_id")) if c.get("document_id") is not None else None,
                "document_title": c.get("document_title") or c.get("title"),
                "score": float(c.get("score", 0.0) or 0.0),
                "preview": _src_preview(c.get("text") or ""),
                "meta": c.get("meta") or {},
            }
        )

    # Default: generate a tiny quick-check MCQ (offline) from the same chunks
    quick_mcq = []
    try:
        quick_mcq = _generate_mcq_from_chunks(topic=topic or "tài liệu", level="beginner", question_count=2, chunks=chunks)
        quick_mcq = clean_mcq_questions(quick_mcq, limit=2)
    except Exception:
        quick_mcq = []

    if llm_available():
        packed = pack_chunks(chunks, max_chunks=min(4, len(chunks)), max_chars_per_chunk=750, max_total_chars=2800)
        sys = (
            "Bạn là Virtual AI Tutor (trợ giảng) cho học sinh, phong cách giống ChatGPT nhưng phải bám tài liệu.\n"
            "CHỈ dựa trên evidence_chunks (không dùng kiến thức ngoài). Không bịa. Không copy nguyên văn dài.\n\n"
            "Yêu cầu trả lời (answer_md) phải CHI TIẾT, có cấu trúc như giáo viên giảng bài:\n"
            "1) Trả lời ngắn gọn (1–2 câu)\n"
            "2) Giải thích chi tiết theo từng ý/bước\n"
            "3) Ví dụ minh hoạ: nếu evidence không có ví dụ cụ thể, hãy ghi rõ là ví dụ giả định\n"
            "4) Lỗi thường gặp / lưu ý\n"
            "5) Tóm tắt 3 ý\n\n"
            "Nếu evidence không đủ để trả lời chắc chắn: hãy trả lời KHÉO (lịch sự), nói rõ thiếu chỗ nào trong tài liệu, "
            "đặt 1–3 câu hỏi để làm rõ và gợi ý học sinh tìm đúng chương/mục.\n\n"
            "Lưu ý: evidence_chunks đã được rerank theo mức độ liên quan với câu hỏi. "
            "Ưu tiên dùng các chunk ở đầu danh sách; nếu các chunk mâu thuẫn/khác nhau, phải nêu rõ và chọn câu trả lời an toàn nhất."
        )
        user = {
            "question": q,
            "topic": (topic or "").strip() or None,
            "evidence_chunks": packed,
            "output_format": {
                "answer_md": "markdown",
                "follow_up_questions": ["string"],
                "quick_check_mcq": [
                    {
                        "type": "mcq",
                        "stem": "string",
                        "options": ["A", "B", "C", "D"],
                        "correct_index": 0,
                        "explanation": "string"
                    }
                ],
            },
        }
        try:
            resp = chat_json(
                messages=[
                    {"role": "system", "content": sys},
                    {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
                ],
                temperature=0.25,
                max_tokens=1200,
            )
            if isinstance(resp, dict) and (resp.get("answer_md") or "").strip():
                answer_md = (resp.get("answer_md") or "").strip()
                fu = [str(x).strip() for x in (resp.get("follow_up_questions") or []) if str(x).strip()]
                mcq = resp.get("quick_check_mcq") or []
                if isinstance(mcq, list) and mcq:
                    try:
                        mcq = clean_mcq_questions(mcq, limit=2)
                    except Exception:
                        mcq = []
                else:
                    mcq = quick_mcq

                data = TutorChatData(
                    answer_md=answer_md,
                    follow_up_questions=fu[:3],
                    quick_check_mcq=mcq[:2],
                    sources=sources,
                    retrieval=rag.get("corrective") or {},
                ).model_dump()
                return data
        except Exception:
            pass

    # Offline fallback: stitch a short answer from top chunks (extractive summary)
    bullets = []
    for c in chunks[:3]:
        txt = " ".join(str(c.get("text") or "").split())
        if len(txt) > 260:
            txt = txt[:257].rstrip() + "…"
        if txt:
            bullets.append(f"- {txt}")
    answer_md = (
        (
            "Mình đang ở chế độ **không dùng LLM**, nên mình sẽ trích các đoạn liên quan nhất trong tài liệu để bạn tự đối chiếu:\n\n"
            + "\n".join(bullets)
            + "\n\nNếu bạn muốn mình giải thích chi tiết hơn: hãy bật LLM hoặc dán đoạn văn cụ thể (10–30 dòng)."
        )
        if bullets
        else (
            "Mình **chưa đủ thông tin trong tài liệu** để trả lời chắc chắn câu này.\n\n"
            "Bạn hãy cho mình thêm: (1) chương/mục đang học, hoặc (2) 1 đoạn trích liên quan — mình sẽ giải thích tiếp."
        )
    )

    data = TutorChatData(
        answer_md=answer_md,
        follow_up_questions=[],
        quick_check_mcq=quick_mcq,
        sources=sources,
        retrieval=rag.get("corrective") or {},
    ).model_dump()
    return data


def tutor_generate_questions(
    db: Session,
    *,
    user_id: int,
    topic: str,
    level: str | None = None,
    question_count: int = 6,
    top_k: int = 8,
    document_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Generate a *fresh* set of practice questions from the teacher's documents.

    Design goal (per user requirement): questions are NOT based on a fixed framework.
    The system should discover what is in the document for the chosen topic and ask
    suitable questions (definitions / steps / formulas / examples / pitfalls / comparisons...).
    """

    ensure_user_exists(db, int(user_id), role="student")

    t = (topic or "").strip()
    if not t:
        raise HTTPException(status_code=422, detail="Missing topic")

    qc = int(question_count or 0)
    qc = max(1, min(20, qc))

    # Auto-scope to teacher docs by default
    doc_ids = list(document_ids or [])
    if not doc_ids:
        auto = auto_document_ids_for_query(db, t, preferred_user_id=settings.DEFAULT_TEACHER_ID, max_docs=3)
        if auto:
            doc_ids = auto

    filters = {"document_ids": doc_ids} if doc_ids else {}

    # Retrieval query: keep it simple (topic only) to avoid imposing a template.
    rag = corrective_retrieve_and_log(
        db=db,
        query=t,
        top_k=int(max(6, min(30, top_k))),
        filters=filters,
        topic=t,
    )

    chunks = rag.get("chunks") or []
    good, bad = filter_chunks_by_quality(chunks, min_score=float(settings.OCR_MIN_QUALITY_SCORE))
    bad_ratio = float(len(bad)) / float(max(1, len(chunks)))
    if (not good) or (bad_ratio >= float(settings.OCR_BAD_CHUNK_RATIO) and len(good) < 2):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "NEED_CLEAN_TEXT",
                "message": "CONTEXT bị lỗi OCR / rời rạc nên không thể sinh câu hỏi chắc chắn.",
                "reason": f"bad_chunk_ratio={bad_ratio:.2f}, good={len(good)}, total={len(chunks)}",
                "suggestion": "Hãy upload file .docx hoặc PDF có text layer / hoặc copy-paste đúng mục cần luyện.",
                "debug": {"sample_bad": bad[:2]},
            },
        )
    chunks = good

    # Build sources for UI/debug
    sources = []
    for c in chunks[: min(len(chunks), int(top_k))]:
        sources.append(
            {
                "chunk_id": int(c.get("chunk_id")),
                "document_id": int(c.get("document_id")) if c.get("document_id") is not None else None,
                "document_title": c.get("document_title") or c.get("title"),
                "score": float(c.get("score", 0.0) or 0.0),
                "preview": _src_preview(c.get("text") or ""),
                "meta": c.get("meta") or {},
            }
        )

    packed = pack_chunks(chunks, max_chunks=min(8, len(chunks)), max_chars_per_chunk=900, max_total_chars=5200)
    valid_ids = [int(c["chunk_id"]) for c in packed] if packed else []

    # Build a compact "topic profile" so the LLM can ask questions based on what's actually in the text.
    body_for_profile = "\n\n".join([str(c.get("text") or "") for c in packed]) if packed else ""
    topic_profile = build_topic_details(body_for_profile, title=t) if body_for_profile.strip() else {
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

    def _tok(s: str) -> set[str]:
        s = (s or "").lower()
        return {w for w in __import__("re").findall(r"[\wÀ-ỹ]+", s) if len(w) >= 3}

    def _best_sources(text_hint: str, k: int = 2) -> List[Dict[str, int]]:
        if not packed:
            return []
        hint = _tok(text_hint)
        scored = []
        for c in packed:
            cid = int(c.get("chunk_id"))
            ct = _tok(f"{c.get('title') or ''} {c.get('text') or ''}")
            scored.append((len(hint & ct), cid))
        scored.sort(reverse=True)
        picked = [cid for score, cid in scored if score > 0][:k]
        if not picked:
            picked = [int(packed[0]["chunk_id"])]
        return [{"chunk_id": int(x)} for x in picked]

    # LLM path: generate varied questions WITHOUT a fixed framework.
    if llm_available() and packed:
        sys = (
            "Bạn là trợ giảng. Nhiệm vụ: sinh bộ CÂU HỎI LUYỆN TẬP dựa CHỈ trên evidence_chunks. "
            "Quan trọng: KHÔNG dùng một 'khung sẵn' (ví dụ: luôn hỏi định nghĩa → quy trình → ưu/nhược...). "
            "Hãy đọc topic_profile và tự chọn góc hỏi phù hợp với nội dung thật sự có trong văn bản. "
            "Nếu topic_profile cho thấy có quy trình/bước làm, hãy hỏi về bước/điều kiện; nếu có công thức, hỏi ý nghĩa và cách áp dụng; "
            "nếu có ví dụ/tình huống, hỏi phân tích; nếu có lỗi thường gặp/misconceptions, hỏi cách phát hiện/sửa. "
            "Không bịa kiến thức ngoài CONTEXT. Không copy nguyên văn dài."
        )

        user = {
            "topic": t,
            "level": (level or "").strip() or None,
            "question_count": qc,
            "topic_profile": topic_profile,
            "evidence_chunks": packed,
            "output_format": {
                "status": "OK|NEED_CLEAN_TEXT",
                "questions": [
                    {
                        "type": "open_ended",
                        "stem": "string",
                        "hints": ["string"],
                        "sources": [{"chunk_id": 123}],
                    }
                ],
            },
            "constraints": [
                "Mỗi câu hỏi phải bám ít nhất 1 chunk_id trong evidence_chunks (sources).",
                "Câu hỏi phải cụ thể, có yêu cầu rõ ràng, tránh mơ hồ.",
                "Không nhắc các từ: chunk, evidence, trích, theo tài liệu.",
                "Các câu phải đa dạng và PHÙ HỢP với nội dung, không lặp ý.",
            ],
        }

        try:
            resp = chat_json(
                messages=[
                    {"role": "system", "content": sys},
                    {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
                ],
                temperature=0.35,
                max_tokens=1600,
            )
        except Exception:
            resp = None

        if isinstance(resp, dict) and str(resp.get("status", "")).upper() == "NEED_CLEAN_TEXT":
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "NEED_CLEAN_TEXT",
                    "message": "CONTEXT không đủ rõ để sinh câu hỏi bám tài liệu.",
                    "reason": resp.get("reason") or resp.get("message") or "CONTEXT bị rời rạc/ký tự lỗi hoặc thiếu thông tin chắc chắn.",
                    "suggestion": resp.get("suggestion") or "Hãy upload file .docx hoặc PDF có text layer / hoặc copy text của mục cần luyện.",
                },
            )

        raw_qs = resp.get("questions") if isinstance(resp, dict) else None
        if isinstance(raw_qs, list) and raw_qs:
            cleaned = []
            seen = set()
            for q in raw_qs:
                if not isinstance(q, dict):
                    continue
                stem = " ".join(str(q.get("stem") or "").split()).strip()
                if len(stem) < 12:
                    continue
                key = stem.lower()
                if key in seen:
                    continue
                seen.add(key)

                hints = [" ".join(str(x).split()).strip() for x in (q.get("hints") or []) if str(x).strip()]
                sources_raw = q.get("sources")
                if isinstance(sources_raw, dict):
                    sources_raw = [sources_raw]
                s_ok: List[Dict[str, int]] = []
                if isinstance(sources_raw, list):
                    for it in sources_raw:
                        cid = it.get("chunk_id") if isinstance(it, dict) else it
                        try:
                            cid_i = int(cid)
                        except Exception:
                            continue
                        if cid_i in valid_ids:
                            s_ok.append({"chunk_id": cid_i})
                s_ok = s_ok[:2]
                if not s_ok:
                    s_ok = _best_sources(f"{t} {stem}", k=2)

                cleaned.append({"type": "open_ended", "stem": stem, "hints": hints[:3], "sources": s_ok})
                if len(cleaned) >= qc:
                    break

            if cleaned:
                return TutorGenerateQuestionsData(
                    topic=t,
                    level=(level or "").strip() or None,
                    questions=cleaned,
                    sources=sources,
                    retrieval=rag.get("corrective") or {},
                ).model_dump()

    # Offline fallback: build questions from the extracted topic_profile.
    questions: List[Dict[str, Any]] = []

    defs = topic_profile.get("definitions") or []
    kps = topic_profile.get("key_points") or []
    exs = topic_profile.get("examples") or []
    misc = topic_profile.get("misconceptions") or []

    def _add(stem: str):
        stem = " ".join((stem or "").split()).strip()
        if len(stem) < 12:
            return
        if any(stem.lower() == q["stem"].lower() for q in questions):
            return
        questions.append({"type": "open_ended", "stem": stem, "hints": [], "sources": _best_sources(stem, k=2)})

    # Pick a few different angles based on what exists in the text.
    if isinstance(defs, list) and defs:
        d0 = defs[0]
        term = (d0.get("term") if isinstance(d0, dict) else "") or t
        _add(f"Hãy giải thích '{term}' theo ý bạn và nêu một ví dụ minh hoạ.")

    if isinstance(kps, list) and kps:
        _add(f"Trong chủ đề '{t}', hãy tóm tắt 3 ý chính quan trọng nhất và giải thích vì sao chúng quan trọng.")

    if isinstance(misc, list) and misc:
        m0 = misc[0]
        _add(f"Nêu một hiểu lầm/sai lầm phổ biến liên quan đến '{t}' và cách tránh.")

    if isinstance(exs, list) and exs:
        _add(f"Hãy phân tích ví dụ trong tài liệu liên quan đến '{t}': mục tiêu, các bước/chọn lựa chính và kết quả.")

    # Fill remaining with general-but-not-fixed prompts.
    while len(questions) < qc:
        idx = len(questions) + 1
        _add(f"Câu {idx}: Hãy đặt một tình huống thực tế và mô tả cách bạn áp dụng '{t}' để giải quyết.")
        if len(questions) >= qc:
            break

    return TutorGenerateQuestionsData(
        topic=t,
        level=(level or "").strip() or None,
        questions=questions[:qc],
        sources=sources,
        retrieval=rag.get("corrective") or {},
    ).model_dump()
