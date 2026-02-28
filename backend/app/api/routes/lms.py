from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.attempt import Attempt
from app.models.classroom_assessment import ClassroomAssessment
from app.models.document_topic import DocumentTopic
from app.models.quiz_set import QuizSet
from app.services.assessment_service import generate_assessment, submit_assessment
from app.services.lms_service import build_recommendations, classify_student_level, score_breakdown

router = APIRouter(tags=["lms"])


class TeacherTopicSelectionIn(BaseModel):
    teacher_id: int
    classroom_id: int
    document_id: int
    topics: list[str] = Field(default_factory=list)


class GenerateLmsQuizIn(BaseModel):
    teacher_id: int
    classroom_id: int
    document_ids: list[int] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    title: str = "Placement Test"
    easy_count: int = 4
    medium_count: int = 4
    hard_count: int = 2


class SubmitAttemptIn(BaseModel):
    user_id: int
    duration_sec: int = 0
    answers: list[dict] = Field(default_factory=list)


@router.post("/lms/teacher/select-topics")
def teacher_select_topics(request: Request, payload: TeacherTopicSelectionIn, db: Session = Depends(get_db)):
    if not payload.topics:
        raise HTTPException(status_code=400, detail="Vui lòng chọn ít nhất 1 topic")

    existing = {
        str(r[0]).strip().lower()
        for r in db.query(DocumentTopic.title).filter(DocumentTopic.document_id == int(payload.document_id)).all()
    }
    selected = [t.strip() for t in payload.topics if t and t.strip()]
    missing = [t for t in selected if t.strip().lower() not in existing]
    return {
        "request_id": request.state.request_id,
        "data": {
            "teacher_id": payload.teacher_id,
            "classroom_id": payload.classroom_id,
            "document_id": payload.document_id,
            "selected_topics": selected,
            "missing_topics": missing,
            "status": "ok",
        },
        "error": None,
    }


def _generate_assessment_lms(*, request: Request, db: Session, payload: GenerateLmsQuizIn, kind: str):
    data = generate_assessment(
        db,
        teacher_id=int(payload.teacher_id),
        classroom_id=int(payload.classroom_id),
        title=payload.title,
        level="intermediate",
        kind=kind,
        easy_count=int(payload.easy_count + payload.medium_count),
        hard_count=int(payload.hard_count),
        document_ids=[int(x) for x in payload.document_ids],
        topics=payload.topics,
    )
    data["difficulty_plan"] = {
        "easy": int(payload.easy_count),
        "medium": int(payload.medium_count),
        "hard": int(payload.hard_count),
    }
    return {"request_id": request.state.request_id, "data": data, "error": None}


@router.post("/lms/placement/generate")
def lms_generate_placement(request: Request, payload: GenerateLmsQuizIn, db: Session = Depends(get_db)):
    payload.title = payload.title or "Placement Test"
    return _generate_assessment_lms(request=request, db=db, payload=payload, kind="diagnostic_pre")


@router.post("/lms/final/generate")
def lms_generate_final(request: Request, payload: GenerateLmsQuizIn, db: Session = Depends(get_db)):
    payload.title = payload.title or "Final Test"
    return _generate_assessment_lms(request=request, db=db, payload=payload, kind="diagnostic_post")


@router.post("/lms/attempts/{assessment_id}/submit")
def lms_submit_attempt(request: Request, assessment_id: int, payload: SubmitAttemptIn, db: Session = Depends(get_db)):
    base = submit_assessment(
        db,
        assessment_id=int(assessment_id),
        user_id=int(payload.user_id),
        duration_sec=int(payload.duration_sec),
        answers=payload.answers,
    )

    breakdown = score_breakdown(base.get("breakdown") or [])
    level = classify_student_level(int(round(float(breakdown["overall"]["percent"]))))

    q = db.query(QuizSet).filter(QuizSet.id == int(assessment_id)).first()
    topics = [str(x) for x in (q.topic.split(",") if q and q.topic else []) if x.strip()]
    recommendations = build_recommendations(breakdown=breakdown, document_topics=topics)

    base["score_breakdown"] = breakdown
    base["student_level"] = level
    base["recommendations"] = recommendations
    return {"request_id": request.state.request_id, "data": base, "error": None}


@router.get("/lms/teacher/report/{classroom_id}")
def teacher_report(request: Request, classroom_id: int, db: Session = Depends(get_db)):
    assessment_ids = [
        int(r[0])
        for r in db.query(ClassroomAssessment.assessment_id)
        .filter(ClassroomAssessment.classroom_id == int(classroom_id))
        .all()
    ]
    if not assessment_ids:
        return {"request_id": request.state.request_id, "data": {"rows": [], "summary": {}}, "error": None}

    attempts = db.query(Attempt).filter(Attempt.quiz_set_id.in_(assessment_ids)).all()
    by_student: dict[int, list[float]] = defaultdict(list)
    by_level: dict[str, int] = defaultdict(int)

    for at in attempts:
        br = score_breakdown(at.breakdown_json or [])
        pct = float(br["overall"]["percent"])
        by_student[int(at.user_id)].append(pct)
        by_level[classify_student_level(int(round(pct)))] += 1

    rows = []
    for uid, vals in sorted(by_student.items()):
        avg = round(sum(vals) / max(1, len(vals)), 2)
        rows.append({"student_id": uid, "attempts": len(vals), "avg_percent": avg, "level": classify_student_level(int(round(avg)))})

    summary = {
        "students": len(rows),
        "attempts": len(attempts),
        "avg_percent": round(sum((r["avg_percent"] for r in rows), 0.0) / max(1, len(rows)), 2),
        "level_distribution": by_level,
    }
    return {"request_id": request.state.request_id, "data": {"rows": rows, "summary": summary}, "error": None}
