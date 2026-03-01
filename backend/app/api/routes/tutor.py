from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.api.deps import require_teacher
from app.db.session import get_db
from app.models.classroom import Classroom
from app.models.user import User
from app.schemas.tutor import TutorChatRequest, TutorGenerateQuestionsRequest
from app.services.tutor_service import get_classroom_tutor_logs, tutor_chat, tutor_generate_questions

router = APIRouter(tags=["tutor"])

def _format_tutor_contract(data: Dict[str, Any], payload: TutorChatRequest) -> Dict[str, Any]:
    follow_ups = [str(x).strip() for x in (data.get("follow_up_questions") or []) if str(x).strip()]
    follow_ups = follow_ups[:3]

    suggested_topics = [str(x).strip() for x in (data.get("suggested_topics") or []) if str(x).strip()]
    scope = payload.topic or (suggested_topics[0] if suggested_topics else "chủ đề đang học")

    reason = str(data.get("refusal_reason") or data.get("off_topic_reason") or "").strip().lower()
    is_off_topic = bool(data.get("is_off_topic"))

    status = "ok"
    if reason == "ocr_quality_too_low":
        status = "need_clean_text"
    elif is_off_topic or reason.startswith("low_relevance") or reason == "no_retrieved_chunks":
        status = "refuse_out_of_scope"

    answer_md = str(data.get("answer_md") or "").strip()
    if status == "refuse_out_of_scope":
        answer_md = (
            "Xin lỗi, câu hỏi này nằm **ngoài phạm vi tài liệu hiện tại** hoặc tài liệu chưa đủ rõ để trả lời chắc chắn.\n\n"
            "Bạn có thể hỏi lại theo mẫu: *'Trong tài liệu hiện tại, hãy giải thích [khái niệm] và nêu ý chính.'*"
        )
        if scope:
            answer_md += f"\n\nGợi ý phạm vi hiện tại: **{scope}**."
    elif status == "need_clean_text" and not answer_md:
        answer_md = "Tài liệu hiện tại bị nhiễu/thiếu nên chưa thể trả lời an toàn. Bạn vui lòng cung cấp bản text sạch hơn."

    if len(follow_ups) < 3:
        defaults = [
            f"Trong phạm vi tài liệu hiện tại, {scope} là gì?",
            f"Các ý chính của {scope} trong tài liệu là gì?",
            f"Có ví dụ nào về {scope} trong tài liệu không?",
        ]
        for q in defaults:
            if q not in follow_ups:
                follow_ups.append(q)
            if len(follow_ups) >= 3:
                break

    srcs: List[Dict[str, Any]] = []
    for s in (data.get("sources") or []):
        if not isinstance(s, dict):
            continue
        try:
            chunk_id = int(s.get("chunk_id"))
        except Exception:
            continue
        srcs.append(
            {
                "chunk_id": chunk_id,
                "preview": str(s.get("preview") or ""),
                "score": float(s.get("score", 0.0) or 0.0),
            }
        )

    return {
        **data,
        "status": status,
        "answer_md": answer_md,
        "follow_up_questions": follow_ups[:3],
        "suggested_questions": [str(x).strip() for x in (data.get("suggested_questions") or follow_ups[:3]) if str(x).strip()][:3],
        "sources": srcs,
    }


@router.post("/v1/tutor/chat")
@router.post("/tutor/chat")
def chat(request: Request, payload: TutorChatRequest, db: Session = Depends(get_db)):
    data = tutor_chat(
        db=db,
        user_id=payload.user_id,
        question=payload.question,
        topic=payload.topic,
        top_k=payload.top_k,
        document_ids=payload.document_ids,
        allowed_topics=payload.allowed_topics,
        assessment_id=payload.assessment_id,
        attempt_id=payload.attempt_id,
        exam_mode=payload.exam_mode,
    )

    # Safety: ensure response is JSON-serializable.
    # Some DB meta fields (or upstream libs) may contain `bytes`, which breaks JSON encoding.
    formatted = _format_tutor_contract(data, payload)

    safe = jsonable_encoder(
        formatted,
        custom_encoder={
            bytes: lambda b: b.decode("utf-8", errors="ignore"),
            bytearray: lambda b: bytes(b).decode("utf-8", errors="ignore"),
            memoryview: lambda b: bytes(b).decode("utf-8", errors="ignore"),
        },
    )
    return {"request_id": request.state.request_id, "data": safe, "error": None}


@router.post("/tutor/generate-questions")
def generate_questions(request: Request, payload: TutorGenerateQuestionsRequest, db: Session = Depends(get_db)):
    """Practice mode: generate questions for the student to answer.

    Key requirement: questions must be derived from the document contents for the chosen topic
    (no fixed/preset question framework).
    """
    data = tutor_generate_questions(
        db=db,
        user_id=payload.user_id,
        topic=payload.topic,
        level=payload.level,
        question_count=payload.question_count,
        top_k=payload.top_k,
        document_ids=payload.document_ids,
        allowed_topics=payload.allowed_topics,
        assessment_id=payload.assessment_id,
        attempt_id=payload.attempt_id,
        exam_mode=payload.exam_mode,
    )

    safe = jsonable_encoder(
        data,
        custom_encoder={
            bytes: lambda b: b.decode("utf-8", errors="ignore"),
            bytearray: lambda b: bytes(b).decode("utf-8", errors="ignore"),
            memoryview: lambda b: bytes(b).decode("utf-8", errors="ignore"),
        },
    )
    return {"request_id": request.state.request_id, "data": safe, "error": None}

@router.get("/teacher/tutor-logs/{classroom_id}")
def teacher_tutor_logs(
    request: Request,
    classroom_id: int,
    flagged: bool = Query(default=False),
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    row = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    if not row or int(row.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=404, detail="Classroom not found")

    data = get_classroom_tutor_logs(db, classroom_id=int(classroom_id), flagged=bool(flagged))
    return {"request_id": request.state.request_id, "data": data, "error": None}

