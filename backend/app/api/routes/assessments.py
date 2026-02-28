from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_teacher, require_user
from app.db.session import get_db
from app.models.classroom import Classroom, ClassroomMember
from app.models.classroom_assessment import ClassroomAssessment
from app.models.attempt import Attempt
from app.models.class_report import ClassReport
from app.models.quiz_set import QuizSet
from app.models.user import User
from app.infra.queue import enqueue
from app.tasks.report_tasks import task_generate_class_final_report
from app.schemas.assessment import (
    AssessmentGenerateRequest,
    AssessmentSubmitRequest,
    TeacherGradeRequest,
)
from app.services.assessment_service import (
    generate_assessment,
    generate_diagnostic_assessment,
    get_assessment,
    submit_assessment,
    start_assessment_session,
    list_assessments_for_teacher,
    list_assessments_for_user,
    list_assessments_by_type,
    leaderboard_for_assessment,
    grade_essays,
    get_latest_submission,
)


router = APIRouter(tags=["assessments"])
teacher_router = APIRouter(tags=["teacher"])




class DiagnosticGenerateRequest(BaseModel):
    classroom_id: int
    topic_ids: list[int] = Field(default_factory=list)
    difficulty_config: dict[str, int] | None = None

def _check_and_trigger_class_report(db: Session, *, assessment_id: int, user_id: int) -> None:
    _ = user_id
    mapping = (
        db.query(ClassroomAssessment, QuizSet)
        .join(QuizSet, QuizSet.id == ClassroomAssessment.assessment_id)
        .filter(ClassroomAssessment.assessment_id == int(assessment_id))
        .first()
    )
    if not mapping:
        return

    classroom_assessment, quiz_set = mapping
    if (quiz_set.kind or "").strip().lower() != "final_exam":
        return

    classroom_id = int(classroom_assessment.classroom_id)
    total_members = (
        db.query(func.count(ClassroomMember.id))
        .filter(ClassroomMember.classroom_id == classroom_id)
        .scalar()
    )
    total_members = int(total_members or 0)
    if total_members <= 0:
        return

    submitted = (
        db.query(func.count(func.distinct(Attempt.user_id)))
        .join(ClassroomMember, ClassroomMember.user_id == Attempt.user_id)
        .filter(ClassroomMember.classroom_id == classroom_id, Attempt.quiz_set_id == int(assessment_id))
        .scalar()
    )
    submitted = int(submitted or 0)
    threshold_reached = (submitted / max(1, total_members)) >= 0.8
    if not threshold_reached:
        return

    exists = (
        db.query(ClassReport.id)
        .filter(ClassReport.classroom_id == classroom_id, ClassReport.assessment_id == int(assessment_id))
        .first()
    )
    if exists:
        return

    enqueue(
        task_generate_class_final_report,
        classroom_id,
        int(assessment_id),
        queue_name="default",
    )


def _student_can_access_assessment(db: Session, *, student_id: int, assessment_id: int) -> bool:
    # student must be member of a classroom that has this assessment assigned
    q = (
        db.query(ClassroomAssessment.id)
        .join(ClassroomMember, ClassroomMember.classroom_id == ClassroomAssessment.classroom_id)
        .filter(ClassroomMember.user_id == int(student_id))
        .filter(ClassroomAssessment.assessment_id == int(assessment_id))
        .limit(1)
    )
    return bool(q.first())


@router.post("/assessments/generate")
def assessments_generate(
    request: Request,
    payload: AssessmentGenerateRequest,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    # Validate classroom ownership
    c = db.query(Classroom).filter(Classroom.id == int(payload.classroom_id)).first()
    if not c or int(c.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=404, detail="Classroom not found")

    try:
        data = generate_assessment(
            db,
            teacher_id=int(teacher.id),
            classroom_id=int(payload.classroom_id),
            title=payload.title,
            level=payload.level,
            easy_count=payload.easy_count,
            hard_count=payload.hard_count,
            document_ids=payload.document_ids,
            topics=payload.topics,
            kind=payload.kind,
        )
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))




@router.post("/assessments/generate-diagnostic")
def assessments_generate_diagnostic(
    request: Request,
    payload: DiagnosticGenerateRequest,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    c = db.query(Classroom).filter(Classroom.id == int(payload.classroom_id)).first()
    if not c or int(c.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=404, detail="Classroom not found")

    try:
        data = generate_diagnostic_assessment(
            db,
            teacher_id=int(teacher.id),
            classroom_id=int(payload.classroom_id),
            topic_ids=[int(t) for t in (payload.topic_ids or [])],
            difficulty_config=payload.difficulty_config or {"easy": 5, "medium": 5, "hard": 5},
        )
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/assessments")
def assessments_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    classroom_id: int | None = None,
):
    # Student: list assessments assigned to their class(es)
    if (getattr(user, "role", "student") or "student") == "student":
        data = list_assessments_for_user(db, user_id=int(user.id), classroom_id=classroom_id)
        return {"request_id": request.state.request_id, "data": data, "error": None}

    # Teacher: list across their classes, optionally filtered
    data = list_assessments_for_teacher(db, teacher_id=int(user.id), classroom_id=classroom_id)
    return {"request_id": request.state.request_id, "data": data, "error": None}


@router.get("/assessments/by-type/{kind}")
def get_assessments_by_type(
    kind: str,
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
):
    """Lấy danh sách bài kiểm tra theo loại: diagnostic_pre, final, homework"""
    allowed = {"diagnostic_pre", "final", "homework", "midterm", "final_exam", "entry_test", "diagnostic_post"}
    if kind not in allowed:
        raise HTTPException(status_code=400, detail=f"kind must be one of {allowed}")
    if kind == "homework":
        return {"request_id": request.state.request_id, "data": [], "error": None}

    data = list_assessments_by_type(db, user_id=int(user_id), kind=kind)
    return {"request_id": request.state.request_id, "data": data, "error": None}


@router.get("/assessments/{assessment_id}")
def assessments_get(
    request: Request,
    assessment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    # Students can only open assessments assigned to their classroom.
    if (getattr(user, "role", "student") or "student") == "student":
        if not _student_can_access_assessment(db, student_id=int(user.id), assessment_id=int(assessment_id)):
            raise HTTPException(status_code=404, detail="Assessment not found")

    try:
        data = get_assessment(db, assessment_id=assessment_id)
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/assessments/{assessment_id}/start")
def assessments_start(
    request: Request,
    assessment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if (getattr(user, "role", "student") or "student") == "student":
        if not _student_can_access_assessment(db, student_id=int(user.id), assessment_id=int(assessment_id)):
            raise HTTPException(status_code=404, detail="Assessment not found")

    try:
        data = start_assessment_session(db, assessment_id=assessment_id, user_id=int(user.id))
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/assessments/{assessment_id}/submit")
def assessments_submit(
    request: Request,
    assessment_id: int,
    payload: AssessmentSubmitRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    # Students can only submit assessments assigned to their classroom.
    if (getattr(user, "role", "student") or "student") == "student":
        if not _student_can_access_assessment(db, student_id=int(user.id), assessment_id=int(assessment_id)):
            raise HTTPException(status_code=404, detail="Assessment not found")

    # Always submit as the current user (ignore payload.user_id)
    try:
        data = submit_assessment(
            db,
            assessment_id=assessment_id,
            user_id=int(user.id),
            answers=[a.model_dump() for a in (payload.answers or [])],
        )
        _check_and_trigger_class_report(db, assessment_id=assessment_id, user_id=int(user.id))
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



@router.post("/assessments/quiz-sets/{quiz_set_id}/submit")
def assessments_submit_quiz_set(
    request: Request,
    quiz_set_id: int,
    payload: AssessmentSubmitRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    return assessments_submit(request=request, assessment_id=quiz_set_id, payload=payload, db=db, user=user)

# -----------------------
# Teacher endpoints
# -----------------------


@teacher_router.get("/teacher/assessments")
def teacher_assessments_list(
    request: Request,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
    classroom_id: int | None = None,
):
    data = list_assessments_for_teacher(db, teacher_id=int(teacher.id), classroom_id=classroom_id)
    return {"request_id": request.state.request_id, "data": data, "error": None}


@teacher_router.get("/teacher/assessments/{assessment_id}/leaderboard")
def teacher_assessment_leaderboard(
    request: Request,
    assessment_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    # (Optional) could validate ownership via classroom mapping; keep permissive for demo.
    try:
        data = leaderboard_for_assessment(db, assessment_id=assessment_id)
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@teacher_router.get("/teacher/assessments/{assessment_id}/submissions/{student_id}")
def teacher_latest_submission(
    request: Request,
    assessment_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    try:
        data = get_latest_submission(db, assessment_id=assessment_id, student_id=student_id)
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@teacher_router.post("/teacher/assessments/{assessment_id}/grade")
def teacher_grade_essays(
    request: Request,
    assessment_id: int,
    payload: TeacherGradeRequest,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    try:
        data = grade_essays(
            db,
            assessment_id=assessment_id,
            student_id=payload.student_id,
            grades=[g.model_dump() for g in (payload.grades or [])],
        )
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
