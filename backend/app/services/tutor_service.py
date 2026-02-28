from __future__ import annotations

import json
import math
import re
import uuid
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent_log import AgentLog
from app.models.classroom import ClassroomMember
from app.models.document_topic import DocumentTopic
from app.models.learning_plan import LearningPlan
from app.schemas.tutor import TutorChatData, TutorGenerateQuestionsData
from app.services.embedding_service import embed_texts
from app.services.user_service import ensure_user_exists
from app.services.corrective_rag import corrective_retrieve_and_log
from app.services.rag_service import auto_document_ids_for_query
from app.services.text_quality import filter_chunks_by_quality
from app.services.llm_service import llm_available, chat_json, pack_chunks
from app.services.quiz_service import clean_mcq_questions, _generate_mcq_from_chunks
from app.services.topic_service import build_topic_details

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None  # type: ignore


OFF_TOPIC_PATTERNS = [
    r"thời tiết|nhiệt độ|dự báo",
    r"ăn gì|nhà hàng|quán|món",
    r"phim|nhạc|ca sĩ|diễn viên",
    r"giá cổ phiếu|tỷ giá|bitcoin",
    r"tình yêu|yêu đương|người yêu",
    r"chính trị|bầu cử|tổng thống",
]

TUTOR_REFUSAL_MESSAGE = """
Xin lỗi, mình chỉ có thể hỗ trợ các câu hỏi **liên quan đến tài liệu học tập**
mà giáo viên đã upload.

Câu hỏi của bạn có vẻ nằm ngoài phạm vi tài liệu hiện tại.

👉 Bạn có thể:
- Hỏi về **lý thuyết, khái niệm, bài tập** trong tài liệu đang học
- Nêu rõ **chủ đề (topic) hoặc chương** bạn cần giải đáp
- Nếu cần hỗ trợ khác, hãy liên hệ giáo viên trực tiếp
""".strip()

_LOCAL_SESSION_STORE: Dict[str, Dict[str, Any]] = {}


def _session_key(user_id: int) -> str:
    return f"tutor:session:{int(user_id)}"


def _get_redis_client():
    if redis is None:
        return None
    try:
        return redis.Redis.from_url(str(getattr(settings, "REDIS_URL", "redis://localhost:6379/0")), decode_responses=True)
    except Exception:
        return None


def _load_tutor_session(user_id: int) -> Dict[str, Any]:
    key = _session_key(user_id)
    cli = _get_redis_client()
    if cli is not None:
        try:
            raw = cli.get(key)
            if raw:
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return dict(_LOCAL_SESSION_STORE.get(key) or {"recent_questions": [], "explained_topics": []})


def _save_tutor_session(user_id: int, data: Dict[str, Any], ttl_sec: int = 60 * 60 * 24) -> None:
    key = _session_key(user_id)
    payload = dict(data or {})
    _LOCAL_SESSION_STORE[key] = payload
    cli = _get_redis_client()
    if cli is not None:
        try:
            cli.setex(key, int(ttl_sec), json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass


def is_clearly_off_topic(question: str) -> bool:
    q_lower = (question or "").lower()
    return any(re.search(p, q_lower) for p in OFF_TOPIC_PATTERNS)


def _suggest_topics(db: Session, *, document_ids: Optional[List[int]], top_k: int = 3) -> List[str]:
    ids = [int(x) for x in (document_ids or []) if x is not None]
    if not ids:
        return []
    rows = (
        db.query(DocumentTopic.display_title, DocumentTopic.title, func.max(DocumentTopic.extraction_confidence).label("conf"))
        .filter(DocumentTopic.document_id.in_(ids))
        .group_by(DocumentTopic.display_title, DocumentTopic.title)
        .order_by(func.max(DocumentTopic.extraction_confidence).desc())
        .limit(int(max(1, top_k)))
        .all()
    )
    out: List[str] = []
    for display_title, title, _ in rows:
        val = str(display_title or title or "").strip()
        if val and val not in out:
            out.append(val)
    return out[:top_k]


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    na = math.sqrt(sum(float(x) * float(x) for x in a))
    nb = math.sqrt(sum(float(y) * float(y) for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return float(dot / (na * nb))


def _intent_aware_topic_suggestions(
    db: Session,
    *,
    question: str,
    topic: Optional[str],
    document_ids: Optional[List[int]],
    top_k: int = 3,
) -> List[str]:
    approved = _suggest_topics(db, document_ids=document_ids, top_k=15)
    if not approved:
        scope = _topic_scope(topic)
        return [scope]
    try:
        vectors = embed_texts([question] + approved)
        if not isinstance(vectors, list) or len(vectors) != len(approved) + 1:
            return approved[:top_k]
        qv = vectors[0]
        scored: List[tuple[float, str]] = []
        for i, name in enumerate(approved, start=1):
            scored.append((_cosine_similarity(qv, vectors[i]), name))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [name for _, name in scored[: max(1, int(top_k))]]
    except Exception:
        return approved[:top_k]


def _build_off_topic_message(*, scope: str, approved_topics: List[str], suggestions: List[str]) -> str:
    approved_text = ", ".join(approved_topics[:8]) if approved_topics else scope
    sug = "\n".join([f"- {x}" for x in suggestions[:3]]) if suggestions else "- " + scope
    return (
        f"Câu hỏi này có vẻ nằm ngoài nội dung **{scope}** chúng ta đang học.\n"
        f"Tôi chỉ có thể giúp bạn về: **{approved_text}**.\n"
        "Bạn muốn hỏi về topic nào trong số này?\n\n"
        "**Gợi ý gần nhất với ý bạn đang hỏi:**\n"
        f"{sug}"
    )


def _extract_referenced_topic(question: str) -> str:
    s = (question or "").strip()
    m = re.search(r"(?:topic|chủ đề)\s+(.+)$", s, flags=re.I)
    if m:
        return m.group(1).strip(" .,:;")
    return s[:120].strip()


def _related_homework_links(db: Session, *, user_id: int, topic: Optional[str], limit: int = 2) -> List[Dict[str, str]]:
    rows = (
        db.query(LearningPlan)
        .filter(LearningPlan.user_id == int(user_id))
        .order_by(LearningPlan.created_at.desc())
        .limit(3)
        .all()
    )
    if not rows:
        return []
    t = (topic or "").lower().strip()
    out: List[Dict[str, str]] = []
    for lp in rows:
        plan = lp.plan_json if isinstance(lp.plan_json, dict) else {}
        days = plan.get("days") if isinstance(plan, dict) else []
        if not isinstance(days, list):
            continue
        for d in days:
            if not isinstance(d, dict):
                continue
            title = str(d.get("title") or "").strip()
            hw = d.get("homework") if isinstance(d.get("homework"), dict) else {}
            stem = str(hw.get("stem") or "").strip()
            hay = f"{title} {stem}".lower()
            if t and (t not in hay):
                continue
            day_index = d.get("day_index")
            try:
                day_int = int(day_index)
            except Exception:
                continue
            out.append(
                {
                    "title": f"Bài tập ngày {day_int}: {title or 'Ôn tập'}",
                    "url": f"/learning-plans/{int(lp.id)}/homework/{int(user_id)}/{day_int}",
                }
            )
            if len(out) >= int(limit):
                return out
    return out[:limit]


def _append_topic_aware_section(
    answer_md: str,
    *,
    topic: Optional[str],
    follow_ups: List[str],
    homework_links: List[Dict[str, str]],
) -> str:
    qlist = [x.strip() for x in (follow_ups or []) if x and x.strip()][:3]
    if len(qlist) < 2:
        scope = _topic_scope(topic)
        qlist.extend(
            [
                f"Khái niệm cốt lõi nào trong {scope} bạn còn thấy mơ hồ?",
                f"Bạn muốn luyện một bài tập ngắn về {scope} không?",
            ]
        )
    qlist = qlist[:3]
    link_lines = [f"- [{it.get('title')}]({it.get('url')})" for it in homework_links if it.get("url")][:2]
    links_md = "\n".join(link_lines) if link_lines else "- Chưa có link bài tập phù hợp trong learning plan hiện tại."
    suggest_md = "\n".join([f"- {x}" for x in qlist])
    return (
        (answer_md or "").rstrip()
        + "\n\n---\n"
        + "### 💡 Xem thêm\n"
        + "**Câu hỏi gợi ý liên quan:**\n"
        + f"{suggest_md}\n\n"
        + "**Bài tập liên quan:**\n"
        + f"{links_md}"
    )


def _log_tutor_flagged_question(
    db: Session,
    *,
    user_id: int,
    question: str,
    topic: Optional[str],
    reason: str,
    suggested_topics: Optional[List[str]] = None,
):
    row = AgentLog(
        event_id=uuid.uuid4().hex,
        event_type="tutor_off_topic",
        agent_name="ai_tutor",
        user_id=int(user_id),
        input_payload={"question": question, "topic": topic},
        output_summary={
            "was_answered": False,
            "off_topic_reason": reason,
            "suggested_topics": suggested_topics or [],
        },
        status="success",
    )
    db.add(row)
    db.commit()


def get_classroom_tutor_logs(db: Session, *, classroom_id: int, flagged: bool = False) -> List[Dict[str, Any]]:
    student_ids = [
        int(uid)
        for (uid,) in db.query(ClassroomMember.user_id)
        .filter(ClassroomMember.classroom_id == int(classroom_id))
        .all()
    ]
    if not student_ids:
        return []

    q = db.query(AgentLog).filter(AgentLog.agent_name == "ai_tutor", AgentLog.user_id.in_(student_ids))
    if flagged:
        q = q.filter(AgentLog.event_type == "tutor_off_topic")
    rows = q.order_by(AgentLog.created_at.desc()).limit(200).all()

    out: List[Dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "id": int(row.id),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "user_id": int(row.user_id) if row.user_id is not None else None,
                "question": (row.input_payload or {}).get("question"),
                "topic": (row.input_payload or {}).get("topic"),
                "event_type": row.event_type,
                "was_answered": (row.output_summary or {}).get("was_answered"),
                "off_topic_reason": (row.output_summary or {}).get("off_topic_reason"),
                "suggested_topics": (row.output_summary or {}).get("suggested_topics") or [],
            }
        )
    return out


def _src_preview(text: str, n: int = 180) -> str:
    s = " ".join(str(text or "").split())
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def _topic_scope(topic: Optional[str]) -> str:
    t = (topic or "").strip()
    return t or "môn học hiện tại"


def _build_redirect_hint(topic: Optional[str]) -> str:
    scope = _topic_scope(topic)
    try:
        samples = [
            f"Khái niệm cốt lõi trong {scope} là gì?",
            f"Bạn có thể giải thích một ví dụ điển hình của {scope} không?",
        ]
        sample_question = "' hoặc '".join(samples[:2])
        return f"Bạn có thể hỏi về '{scope}', ví dụ: '{sample_question}'"
    except Exception:
        return f"Bạn có thể hỏi về '{scope}', ví dụ: 'Khái niệm cốt lõi trong {scope} là gì?'"


def _tokenize_vi(text: str) -> set[str]:
    return {w for w in re.findall(r"[\wÀ-ỹ]+", (text or "").lower()) if len(w) >= 3}


def _is_practice_request(question: str) -> bool:
    q = (question or "").lower()
    return any(k in q for k in ["kiểm tra tôi", "practice with tutor", "đặt câu hỏi", "quiz tôi", "hỏi tôi về"])


def _generate_practice_question(topic: str, chunks: List[Dict[str, Any]]) -> str:
    if llm_available() and chunks:
        packed = pack_chunks(chunks, max_chunks=min(3, len(chunks)), max_chars_per_chunk=600, max_total_chars=1800)
        try:
            out = chat_json(
                messages=[
                    {"role": "system", "content": "Bạn là gia sư. Tạo 1 câu hỏi kiểm tra ngắn, rõ ràng, bám sát tài liệu. Trả JSON {stem:string}."},
                    {"role": "user", "content": json.dumps({"topic": topic, "evidence_chunks": packed}, ensure_ascii=False)},
                ],
                temperature=0.2,
                max_tokens=180,
            )
            stem = str((out or {}).get("stem") or "").strip()
            if stem:
                return stem
        except Exception:
            pass
    t = (topic or "chủ đề này").strip()
    return f"Hãy nêu 2 ý quan trọng nhất của {t} và cho 1 ví dụ minh hoạ ngắn."


def _grade_practice_answer(*, topic: str, question: str, answer: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    if llm_available() and chunks:
        packed = pack_chunks(chunks, max_chunks=min(3, len(chunks)), max_chars_per_chunk=600, max_total_chars=1800)
        try:
            out = chat_json(
                messages=[
                    {"role": "system", "content": "Bạn là gia sư chấm nhanh. Trả JSON {score:int(0|1), feedback:string, explanation:string}."},
                    {
                        "role": "user",
                        "content": json.dumps({"topic": topic, "question": question, "student_answer": answer, "evidence_chunks": packed}, ensure_ascii=False),
                    },
                ],
                temperature=0.0,
                max_tokens=280,
            )
            if isinstance(out, dict):
                return {
                    "score": int(1 if int(out.get("score", 0) or 0) > 0 else 0),
                    "feedback": str(out.get("feedback") or ""),
                    "explanation": str(out.get("explanation") or ""),
                }
        except Exception:
            pass
    ans_len = len((answer or "").strip())
    ok = 1 if ans_len >= 40 else 0
    return {
        "score": ok,
        "feedback": "Trả lời khá ổn." if ok else "Câu trả lời còn ngắn, cần bổ sung ý chính.",
        "explanation": "Hãy nêu rõ khái niệm chính, ví dụ và lưu ý sai thường gặp.",
    }


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

    session = _load_tutor_session(int(user_id))
    recent_questions = [str(x).strip() for x in (session.get("recent_questions") or []) if str(x).strip()]
    explained_topics = [str(x).strip() for x in (session.get("explained_topics") or []) if str(x).strip()]

    doc_ids = list(document_ids or [])
    if not doc_ids:
        auto = auto_document_ids_for_query(db, topic or q, preferred_user_id=settings.DEFAULT_TEACHER_ID, max_docs=3)
        if auto:
            doc_ids = auto

    suggested_topics = _suggest_topics(db, document_ids=doc_ids, top_k=6)
    intent_suggestions = _intent_aware_topic_suggestions(db, question=q, topic=topic, document_ids=doc_ids, top_k=3)

    practice = session.get("practice") if isinstance(session.get("practice"), dict) else {}
    if _is_practice_request(q) and not (practice.get("awaiting_answer")):
        p_topic = _extract_referenced_topic(q) or (topic or "chủ đề hiện tại")
        rag_p = corrective_retrieve_and_log(db=db, query=p_topic, top_k=6, filters={"document_ids": doc_ids} if doc_ids else {}, topic=p_topic)
        p_chunks = rag_p.get("chunks") or []
        stem = _generate_practice_question(p_topic, p_chunks)
        session["practice"] = {"active": True, "topic": p_topic, "score": int(practice.get("score", 0) or 0), "asked": int(practice.get("asked", 0) or 0) + 1, "awaiting_answer": True, "current_question": stem}
        session["recent_questions"] = (recent_questions + [q])[-5:]
        _save_tutor_session(int(user_id), session)
        return TutorChatData(answer_md=(f"🎯 **Practice with Tutor**\n\nCâu hỏi: {stem}\n\nBạn hãy trả lời, mình sẽ chấm và giải thích ngay."), was_answered=True, suggested_topics=intent_suggestions, follow_up_questions=[], quick_check_mcq=[], sources=[], retrieval={"mode": "practice_start"}).model_dump()

    if practice.get("active") and practice.get("awaiting_answer"):
        p_topic = str(practice.get("topic") or topic or "chủ đề hiện tại")
        stem = str(practice.get("current_question") or "")
        rag_p = corrective_retrieve_and_log(db=db, query=p_topic, top_k=6, filters={"document_ids": doc_ids} if doc_ids else {}, topic=p_topic)
        grade = _grade_practice_answer(topic=p_topic, question=stem, answer=q, chunks=rag_p.get("chunks") or [])
        score = int(practice.get("score", 0) or 0) + int(grade.get("score", 0) or 0)
        asked = int(practice.get("asked", 1) or 1)
        session["practice"] = {"active": False, "topic": p_topic, "score": score, "asked": asked, "awaiting_answer": False, "current_question": None}
        db.add(AgentLog(event_id=uuid.uuid4().hex, event_type="tutor_practice_summary", agent_name="ai_tutor", user_id=int(user_id), input_payload={"topic": p_topic}, output_summary={"score": score, "asked": asked}, status="success"))
        db.commit()
        session["recent_questions"] = (recent_questions + [q])[-5:]
        _save_tutor_session(int(user_id), session)
        ans = (
            f"✅ **Chấm bài Practice**\n- Kết quả câu này: **{int(grade.get('score', 0))}/1**\n"
            f"- Nhận xét: {grade.get('feedback') or 'Ổn.'}\n"
            f"- Giải thích: {grade.get('explanation') or ''}\n\n"
            f"📊 Mini-session hiện tại: **{score}/{asked}**.\n"
            f"Bạn có thể yêu cầu: *'Hãy đặt câu hỏi để kiểm tra tôi về topic {p_topic}'* để làm câu tiếp theo."
        )
        return TutorChatData(answer_md=ans, was_answered=True, suggested_topics=[p_topic], follow_up_questions=[], quick_check_mcq=[], sources=[], retrieval={"mode": "practice_grade", "score": score, "asked": asked}).model_dump()

    if is_clearly_off_topic(q):
        reason = "clearly_off_topic_pattern"
        _log_tutor_flagged_question(db, user_id=int(user_id), question=q, topic=topic, reason=reason, suggested_topics=intent_suggestions)
        return TutorChatData(answer_md=_build_off_topic_message(scope=_topic_scope(topic), approved_topics=suggested_topics, suggestions=intent_suggestions), was_answered=False, off_topic_reason=reason, suggested_topics=intent_suggestions, follow_up_questions=[], quick_check_mcq=[], sources=[], retrieval={"note": "PRECHECK_OFF_TOPIC_PATTERN"}).model_dump()

    filters = {"document_ids": doc_ids} if doc_ids else {}
    query = f"{topic.strip()}: {q}" if topic and topic.strip() else q
    rag = corrective_retrieve_and_log(db=db, query=query, top_k=int(max(3, min(20, top_k))), filters=filters, topic=topic)

    corr = rag.get("corrective") or {}
    attempts = corr.get("attempts") or []
    last_try = attempts[-1] if isinstance(attempts, list) and attempts else {}
    try:
        best_rel = float(last_try.get("best_relevance", 0.0) or 0.0)
    except Exception:
        best_rel = 0.0

    chunks = rag.get("chunks") or []
    relevance_threshold = float(settings.CRAG_MIN_RELEVANCE) * 0.55
    has_low_relevance = bool(chunks) and best_rel < relevance_threshold
    if (not chunks) or has_low_relevance:
        reason = "no_retrieved_chunks" if not chunks else f"low_relevance:{best_rel:.3f}"
        _log_tutor_flagged_question(db, user_id=int(user_id), question=q, topic=topic, reason=reason, suggested_topics=intent_suggestions)
        return TutorChatData(answer_md=_build_off_topic_message(scope=_topic_scope(topic), approved_topics=suggested_topics, suggestions=intent_suggestions), was_answered=False, off_topic_reason=reason, suggested_topics=intent_suggestions, follow_up_questions=[], quick_check_mcq=[], sources=[], retrieval={**corr, "note": "POSTCHECK_OFF_TOPIC"}).model_dump()

    good, bad = filter_chunks_by_quality(chunks, min_score=float(settings.OCR_MIN_QUALITY_SCORE))
    bad_ratio = float(len(bad)) / float(max(1, len(chunks)))
    if (not good) or (bad_ratio >= float(settings.OCR_BAD_CHUNK_RATIO) and len(good) < 2):
        msg = (
            "Mình chưa thể trả lời chắc chắn vì phần tài liệu mình truy xuất được đang bị **lỗi OCR / rời rạc** (chữ bị vỡ, thiếu dấu, sai dòng).\n\n"
            "Bạn có thể upload lại file .docx/PDF có text layer, hoặc dán 10–30 dòng liên quan để mình giải thích tốt hơn."
        )
        return TutorChatData(answer_md=msg, was_answered=False, off_topic_reason="ocr_quality_too_low", suggested_topics=intent_suggestions, follow_up_questions=[], quick_check_mcq=[], sources=[], retrieval={**(rag.get("corrective") or {}), "note": "OCR_QUALITY_TOO_LOW"}).model_dump()
    chunks = good

    sources = []
    for c in chunks[: min(len(chunks), int(top_k))]:
        sources.append({"chunk_id": int(c.get("chunk_id")), "document_id": int(c.get("document_id")) if c.get("document_id") is not None else None, "document_title": c.get("document_title") or c.get("title"), "score": float(c.get("score", 0.0) or 0.0), "preview": _src_preview(c.get("text") or ""), "meta": c.get("meta") or {}})

    quick_mcq = []
    try:
        quick_mcq = clean_mcq_questions(_generate_mcq_from_chunks(topic=topic or "tài liệu", level="beginner", question_count=2, chunks=chunks), limit=2)
    except Exception:
        quick_mcq = []

    prev_note = ""
    if recent_questions:
        prev = recent_questions[-1]
        if _tokenize_vi(prev) & _tokenize_vi(q):
            prev_note = f"Ở câu hỏi trước bạn hỏi về: '{prev}'. Câu này có liên quan nên mình nối tiếp phần cũ.\n\n"

    if llm_available():
        packed = pack_chunks(chunks, max_chunks=min(4, len(chunks)), max_chars_per_chunk=750, max_total_chars=2800)
        sys = (
            "Bạn là Virtual AI Tutor. Chỉ dựa trên evidence_chunks. Không bịa. "
            "Nếu chủ đề đã giải thích trong session_history.explained_topics thì tránh lặp lại định nghĩa dài, chỉ nhắc nhanh và đi vào phần mới."
        )
        user = {"question": q, "topic": (topic or "").strip() or None, "session_history": {"recent_questions": recent_questions[-5:], "explained_topics": explained_topics[-8:]}, "evidence_chunks": packed, "output_format": {"answer_md": "markdown", "follow_up_questions": ["string"], "quick_check_mcq": []}}
        try:
            resp = chat_json(messages=[{"role": "system", "content": sys}, {"role": "user", "content": json.dumps(user, ensure_ascii=False)}], temperature=0.25, max_tokens=1200)
            if isinstance(resp, dict) and (resp.get("answer_md") or "").strip():
                answer_md = prev_note + str(resp.get("answer_md") or "").strip()
                fu = [str(x).strip() for x in (resp.get("follow_up_questions") or []) if str(x).strip()]
                answer_md = _append_topic_aware_section(answer_md, topic=topic, follow_ups=fu, homework_links=_related_homework_links(db, user_id=int(user_id), topic=topic))
                if topic:
                    explained_topics = (explained_topics + [topic])[-8:]
                session["recent_questions"] = (recent_questions + [q])[-5:]
                session["explained_topics"] = explained_topics
                _save_tutor_session(int(user_id), session)
                return TutorChatData(answer_md=answer_md, was_answered=True, off_topic_reason=None, suggested_topics=intent_suggestions, follow_up_questions=fu[:3], quick_check_mcq=(quick_mcq[:2]), sources=sources, retrieval=rag.get("corrective") or {}).model_dump()
        except Exception:
            pass

    bullets = []
    for c in chunks[:3]:
        txt = " ".join(str(c.get("text") or "").split())
        if len(txt) > 260:
            txt = txt[:257].rstrip() + "…"
        if txt:
            bullets.append(f"- {txt}")
    answer_md = (
        ("Mình đang ở chế độ **không dùng LLM**. Các đoạn liên quan nhất:\n\n" + "\n".join(bullets))
        if bullets
        else "Mình **chưa đủ thông tin trong tài liệu** để trả lời chắc chắn câu này."
    )
    answer_md = _append_topic_aware_section(prev_note + answer_md, topic=topic, follow_ups=[], homework_links=_related_homework_links(db, user_id=int(user_id), topic=topic))
    if topic:
        explained_topics = (explained_topics + [topic])[-8:]
    session["recent_questions"] = (recent_questions + [q])[-5:]
    session["explained_topics"] = explained_topics
    _save_tutor_session(int(user_id), session)
    return TutorChatData(answer_md=answer_md, was_answered=bool(bullets), off_topic_reason=None if bullets else "insufficient_context", suggested_topics=intent_suggestions, follow_up_questions=[], quick_check_mcq=quick_mcq, sources=sources, retrieval=rag.get("corrective") or {}).model_dump()


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
