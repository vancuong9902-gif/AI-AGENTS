from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import require_teacher, require_user
from app.db.session import get_db
from app.models.classroom import Classroom, ClassroomMember
from app.models.classroom_assessment import ClassroomAssessment
from app.models.user import User
from app.schemas.assessment import (
    AssessmentGenerateRequest,
    AssessmentSubmitRequest,
    TeacherGradeRequest,
)
from app.services.assessment_service import (
    generate_assessment,
    get_assessment,
    submit_assessment,
    list_assessments_for_teacher,
    list_assessments_for_user,
    leaderboard_for_assessment,
    grade_essays,
    get_latest_submission,
)


router = APIRouter(tags=["assessments"])
teacher_router = APIRouter(tags=["teacher"])


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
            duration_sec=payload.duration_sec,
            answers=[a.model_dump() for a in (payload.answers or [])],
        )
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
