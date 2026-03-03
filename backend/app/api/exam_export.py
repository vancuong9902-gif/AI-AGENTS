from __future__ import annotations

from io import BytesIO
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_teacher
from app.models.classroom import Classroom
from app.models.document_topic import DocumentTopic
from app.models.question import Question
from app.models.quiz_set import QuizSet
from app.models.student_assignment import StudentAssignment
from app.models.user import User
from app.services.exam_word_service import generate_exam_word

router = APIRouter(tags=["exam-export"])


class ExamExportRequest(BaseModel):
    num_versions: int = Field(default=1, ge=1, le=5)
    questions_per_exam: int = Field(default=10, ge=10, le=50)
    exam_type: Literal["multiple_choice", "essay", "mixed"] = "multiple_choice"
    difficulty: Literal["easy", "medium", "hard", "mixed"] = "mixed"
    topic_ids: list[int] | None = None
    include_answer_key: bool = True


def _difficulty_matches(level: str, requested: str) -> bool:
    current = str(level or "").lower()
    if requested == "mixed":
        return True
    if requested == "easy":
        return current in {"beginner", "easy"}
    if requested == "medium":
        return current in {"intermediate", "medium"}
    if requested == "hard":
        return current in {"advanced", "hard"}
    return True


@router.get("/teacher/classrooms/{classroom_id}/exam-topics")
def get_exam_topics(
    classroom_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    classroom = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    if not classroom or int(classroom.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=404, detail="Classroom not found")

    topic_ids = {
        int(tid)
        for tid, in db.query(StudentAssignment.topic_id).filter(
            StudentAssignment.classroom_id == int(classroom_id),
            StudentAssignment.topic_id.isnot(None),
        ).distinct().all()
        if tid
    }
    if not topic_ids:
        return {"data": []}

    rows = db.query(DocumentTopic.id, DocumentTopic.teacher_edited_title, DocumentTopic.title).filter(DocumentTopic.id.in_(topic_ids)).all()
    return {
        "data": [
            {"id": int(topic_id), "title": str(edited or title or f"Topic #{topic_id}")}
            for topic_id, edited, title in rows
        ]
    }


@router.post("/teacher/classrooms/{classroom_id}/export-exam")
def export_exam_word(
    classroom_id: int,
    payload: ExamExportRequest,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    classroom = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    if not classroom or int(classroom.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=404, detail="Classroom not found")

    topic_titles: list[str] = []
    if payload.topic_ids:
        rows = (
            db.query(DocumentTopic.teacher_edited_title, DocumentTopic.title)
            .filter(DocumentTopic.id.in_([int(x) for x in payload.topic_ids]))
            .all()
        )
        topic_titles = [str(edited or title or "").strip() for edited, title in rows if str(edited or title or "").strip()]

    query = (
        db.query(Question, QuizSet)
        .join(QuizSet, QuizSet.id == Question.quiz_set_id)
        .filter(QuizSet.user_id == int(teacher.id))
        .order_by(Question.created_at.desc())
    )

    if payload.exam_type != "mixed":
        q_type = "mcq" if payload.exam_type == "multiple_choice" else "essay"
        query = query.filter(Question.type == q_type)

    rows = query.limit(1200).all()
    prepared: list[dict] = []

    for question, quiz_set in rows:
        if topic_titles:
            topic_text = str(getattr(quiz_set, "topic", "") or "").lower()
            if not any(t.lower() in topic_text for t in topic_titles):
                continue

        if not _difficulty_matches(getattr(quiz_set, "level", ""), payload.difficulty):
            continue

        q_type = "multiple_choice" if str(question.type).lower() == "mcq" else "essay"
        options = list(question.options or [])
        correct_index = int(getattr(question, "correct_index", 0) or 0)
        correct_answer = ""
        if q_type == "multiple_choice" and options:
            if 0 <= correct_index < len(options):
                correct_answer = str(options[correct_index])

        prepared.append(
            {
                "question_text": str(question.stem or "").strip(),
                "type": q_type,
                "options": options,
                "correct_answer": correct_answer,
            }
        )

    if len(prepared) < int(payload.questions_per_exam):
        raise HTTPException(status_code=400, detail="Không đủ câu hỏi theo bộ lọc đã chọn")

    selected = prepared[: int(payload.questions_per_exam)]
    file_bytes, filename = generate_exam_word(
        selected,
        num_versions=int(payload.num_versions),
        include_answer_key=bool(payload.include_answer_key),
    )

    media_type = "application/zip" if filename.endswith(".zip") else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return StreamingResponse(
        BytesIO(file_bytes),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
