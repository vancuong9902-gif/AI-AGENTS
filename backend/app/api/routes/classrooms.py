from __future__ import annotations

import random
from io import BytesIO
import string
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.api.deps import get_db, require_teacher, require_user
from app.models.attempt import Attempt
from app.models.classroom import Classroom, ClassroomMember
from app.models.mvp import Course, Topic
from app.models.classroom import Classroom, ClassroomStudent
from app.models.class_report import ClassReport
from app.models.classroom_assessment import ClassroomAssessment
from app.models.document_topic import DocumentTopic
from app.models.learning_plan import LearningPlan, LearningPlanHomeworkSubmission, LearningPlanTaskCompletion
from app.models.quiz_set import QuizSet
from app.models.notification import Notification
from app.models.user import User
from app.schemas.classrooms import (
    AssignLearningPlanRequest,
    ClassroomCreateRequest,
    ClassroomDashboardOut,
    ClassroomEntryTestCreateRequest,
    ClassroomJoinRequest,
    ClassroomOut,
    StudentProgressRow,
)
from app.services.assessment_service import generate_assessment
from app.services.excel_report_service import generate_class_report_excel
from app.services.learning_plan_service import build_teacher_learning_plan
from app.services.learning_plan_storage_service import save_teacher_plan
from app.services.lms_service import analyze_topic_weak_points, classify_student_level, generate_class_narrative, resolve_student_name, score_breakdown
from app.services.pdf_report_service import generate_class_report_pdf
from app.services.report_exporter import export_class_report_docx, export_class_report_pdf, make_export_path
from app.services.user_service import ensure_user_exists


router = APIRouter(tags=["classrooms"])


def _mk_join_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(int(length)))


def _classroom_out(db: Session, c: Classroom, has_content: bool = False) -> ClassroomOut:
    cnt = (
        db.query(func.count(ClassroomStudent.id))
        .filter(ClassroomStudent.classroom_id == int(c.id))
        .scalar()
    )
    return ClassroomOut(
        id=int(c.id),
        name=str(c.name),
        invite_code=str(c.invite_code),
        join_code=str(c.invite_code),
        teacher_id=int(c.teacher_id),
        student_count=int(cnt or 0),
        has_content=bool(has_content),
    )


@router.post("/teacher/classrooms")
def create_classroom(
    request: Request,
    payload: ClassroomCreateRequest,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    # Generate unique join code
    for _ in range(12):
        code = _mk_join_code(8)
        if not db.query(Classroom).filter(Classroom.invite_code == code).first():
            break
    else:
        raise HTTPException(status_code=500, detail="Failed to generate join code")

    row = Classroom(teacher_id=int(teacher.id), name=payload.name.strip(), description=(payload.description or "").strip() or None, course_id=payload.course_id, invite_code=code)
    db.add(row)
    db.commit()
    db.refresh(row)

    out = _classroom_out(db, row).model_dump()
    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": out, "error": None}


@router.get("/teacher/classrooms")
def list_teacher_classrooms(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    q = db.query(Classroom).filter(Classroom.teacher_id == int(teacher.id))
    total = q.count()
    rows = q.order_by(Classroom.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    out = [_classroom_out(db, c).model_dump() for c in rows]
    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": {"items": out, "pagination": {"page": page, "page_size": page_size, "total": total}}, "error": None}


@router.get("/teacher/classrooms/{classroom_id}")
def get_teacher_classroom(
    request: Request,
    classroom_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    c = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    if not c or int(c.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=404, detail="Classroom not found")
    out = _classroom_out(db, c).model_dump()
    student_rows = (
        db.query(ClassroomStudent, User)
        .join(User, User.id == ClassroomStudent.student_id)
        .filter(ClassroomStudent.classroom_id == int(c.id))
        .order_by(User.full_name.asc(), User.id.asc())
        .all()
    )
    students = [{
        "id": int(u.id),
        "full_name": str(u.full_name or ''),
        "email": str(u.email or ''),
        "placement_score": cs.placement_score,
        "final_score": cs.final_score,
        "level": cs.level,
    } for cs, u in student_rows]
    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": {**out, "students": students}, "error": None}


@router.post("/student/classrooms/join")
def join_classroom(
    request: Request,
    payload: ClassroomJoinRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    code = payload.invite_code.strip().upper()
    c = db.query(Classroom).filter(Classroom.invite_code == code).first()
    if not c:
        raise HTTPException(status_code=404, detail="Invalid join code")

    # Ensure this demo user exists and is student-like
    ensure_user_exists(db, int(user.id), role=getattr(user, "role", "student") or "student")

    existing = (
        db.query(ClassroomStudent)
        .filter(ClassroomStudent.classroom_id == int(c.id), ClassroomStudent.student_id == int(user.id))
        .first()
    )
    if not existing:
        db.add(ClassroomStudent(classroom_id=int(c.id), user_id=int(user.id)))
        db.commit()

    out = _classroom_out(db, c).model_dump()
    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": out, "error": None}


@router.get("/student/classrooms")
def list_my_classrooms(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    role = str(getattr(user, "role", "") or "").lower()
    if role == "teacher":
        q = db.query(Classroom).filter(Classroom.teacher_id == int(user.id))
        total = q.count()
        rows = q.order_by(Classroom.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        out = [_classroom_out(db, c).model_dump() for c in rows]
        return {"request_id": getattr(request.state, "request_id", "n/a"), "data": {"items": out, "pagination": {"page": page, "page_size": page_size, "total": total}}, "error": None}

    ids = db.query(ClassroomStudent.classroom_id).filter(ClassroomStudent.student_id == int(user.id)).all()
    cids = [int(x[0]) for x in ids if x and x[0] is not None]
    if not cids:
        return {"request_id": request.state.request_id, "data": [], "error": None}
    rows = db.query(Classroom).filter(Classroom.id.in_(cids)).order_by(Classroom.created_at.desc()).all()

    has_course_attr = hasattr(Classroom, "course_id")
    fallback_course = db.query(Course).order_by(Course.id.desc()).first()
    fallback_has_content = bool(
        fallback_course
        and db.query(Topic).filter(Topic.course_id == int(fallback_course.id)).count() > 0
    )

    out = []
    for c in rows:
        class_has_content = False
        if has_course_attr:
            class_course_id = getattr(c, "course_id", None)
            if class_course_id is not None:
                class_has_content = db.query(Topic).filter(Topic.course_id == int(class_course_id)).count() > 0
        else:
            class_has_content = fallback_has_content
        out.append(_classroom_out(db, c, has_content=class_has_content).model_dump())

    return {"request_id": request.state.request_id, "data": out, "error": None}
        return {"request_id": getattr(request.state, "request_id", "n/a"), "data": {"items": [], "pagination": {"page": page, "page_size": page_size, "total": 0}}, "error": None}
    q = db.query(Classroom).filter(Classroom.id.in_(cids))
    total = q.count()
    rows = q.order_by(Classroom.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    out = [_classroom_out(db, c).model_dump() for c in rows]
    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": {"items": out, "pagination": {"page": page, "page_size": page_size, "total": total}}, "error": None}


def _compute_tasks_total(plan_json: Dict) -> int:
    try:
        days = plan_json.get("days") if isinstance(plan_json, dict) else None
        if not isinstance(days, list):
            return 0
        total = 0
        for d in days:
            if not isinstance(d, dict):
                continue
            tasks = d.get("tasks")
            if isinstance(tasks, list):
                total += len(tasks)
        return int(total)
    except Exception:
        return 0


def _homework_stats(db: Session, plan_id: int, user_id: int) -> Tuple[Optional[float], Optional[float]]:
    rows = (
        db.query(LearningPlanHomeworkSubmission)
        .filter(LearningPlanHomeworkSubmission.plan_id == int(plan_id), LearningPlanHomeworkSubmission.user_id == int(user_id))
        .order_by(LearningPlanHomeworkSubmission.day_index.asc())
        .all()
    )
    if not rows:
        return None, None

    scores: List[float] = []
    last: Optional[float] = None
    for r in rows:
        g = r.grade_json or {}
        try:
            sp = float(g.get("score_points", 0) or 0)
            mp = float(g.get("max_points", 0) or 0)
            pct = (sp / mp * 100.0) if mp > 0 else 0.0
        except Exception:
            pct = 0.0
        scores.append(pct)
        last = pct
    avg = sum(scores) / max(1, len(scores))
    return float(avg), float(last) if last is not None else None


def _build_latest_report_data(db: Session, classroom_id: int) -> dict:
    assessment_ids = [
        int(r[0])
        for r in db.query(ClassroomAssessment.assessment_id)
        .filter(ClassroomAssessment.classroom_id == int(classroom_id))
        .all()
    ]
    attempts = db.query(Attempt).filter(Attempt.quiz_set_id.in_(assessment_ids)).all() if assessment_ids else []
    quiz_kind_map = {
        int(qid): str(kind or "")
        for qid, kind in db.query(QuizSet.id, QuizSet.kind).filter(QuizSet.id.in_(assessment_ids)).all()
    } if assessment_ids else {}

    members = db.query(ClassroomStudent).filter(ClassroomStudent.classroom_id == int(classroom_id)).all()
    student_ids = sorted({int(m.user_id) for m in members})
    pre_scores: dict[int, float] = {}
    post_scores: dict[int, float] = {}
    all_breakdowns: list[dict] = []

    for at in attempts:
        uid = int(at.user_id)
        br = score_breakdown(at.breakdown_json or [])
        all_breakdowns.append(br)
        pct = float((br.get("overall") or {}).get("percent") or 0.0)
        kind = quiz_kind_map.get(int(at.quiz_set_id), "")
        if kind == "diagnostic_pre":
            pre_scores[uid] = pct
        elif kind == "diagnostic_post":
            post_scores[uid] = pct

    students = []
    level_dist = {"gioi": 0, "kha": 0, "trung_binh": 0, "yeu": 0}
    deltas: list[float] = []
    improved_count = 0

    for uid in student_ids:
        entry = float(pre_scores.get(uid, 0.0))
        final = float(post_scores.get(uid, 0.0))
        delta = final - entry
        level = classify_student_level(int(round(final if final > 0 else entry)))
        level_key = str(level["level_key"])
        level_dist[level_key] = int(level_dist.get(level_key, 0)) + 1
        deltas.append(delta)
        if delta > 0:
            improved_count += 1
        students.append(
            {
                "student_id": int(uid),
                "name": resolve_student_name(uid, db),
                "entry_score": entry,
                "final_score": final,
                "level": level_key,
            }
        )

    weak_topics_raw = analyze_topic_weak_points(all_breakdowns) if all_breakdowns else []
    weak_topics = [
        {
            "topic": str(item.get("topic") or "N/A"),
            "avg_pct": float(item.get("avg_pct") or 0.0),
            "suggestion": f"Ôn tập trọng tâm chủ đề {item.get('topic') or 'này'} bằng 3-5 bài luyện ngắn.",
        }
        for item in weak_topics_raw[:5]
    ]

    avg_delta = sum(deltas) / max(1, len(deltas)) if deltas else 0.0
    narrative = generate_class_narrative(
        total_students=len(students),
        level_dist=level_dist,
        weak_topics=weak_topics[:3],
        avg_improvement=avg_delta,
        per_student_data=[],
    )

    return {
        "narrative": narrative,
        "level_dist": level_dist,
        "weak_topics": weak_topics,
        "students": students,
        "improvement": {"avg_delta": avg_delta, "improved_count": improved_count},
    }


def _build_export_students(db: Session, classroom_id: int) -> list[dict]:
    report_data = _build_latest_report_data(db=db, classroom_id=int(classroom_id))
    member_ids = [
        int(row[0])
        for row in db.query(ClassroomMember.user_id)
        .filter(ClassroomMember.classroom_id == int(classroom_id))
        .all()
    ]
    users = db.query(User).filter(User.id.in_(member_ids)).all() if member_ids else []
    email_by_id = {int(u.id): str(u.email or "") for u in users}

    students: list[dict] = []
    for item in report_data.get("students") or []:
        student_id = int(item.get("student_id") or 0)
        students.append(
            {
                "name": str(item.get("name") or ""),
                "email": email_by_id.get(student_id, ""),
                "placement_score": float(item.get("entry_score") or 0.0),
                "final_score": float(item.get("final_score") or 0.0),
                "level": str(item.get("level") or "N/A"),
                "study_hours": 0.0,
                "ai_comment": "",
            }
        )
    return students


@router.get("/teacher/classrooms/{classroom_id}/report/pdf")
def export_teacher_classroom_pdf(
    classroom_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    classroom = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    if not classroom or int(classroom.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=404, detail="Classroom not found")

    students_data = _build_export_students(db=db, classroom_id=int(classroom_id))
    content = generate_class_report_pdf(
        classroom_data={"id": int(classroom.id), "name": str(classroom.name or f"#{classroom_id}")},
        students_data=students_data,
    )
    headers = {"Content-Disposition": f'attachment; filename="classroom_{classroom_id}_report.pdf"'}
    return StreamingResponse(BytesIO(content), media_type="application/pdf", headers=headers)


@router.get("/teacher/classrooms/{classroom_id}/report/excel")
def export_teacher_classroom_excel(
    classroom_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    classroom = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    if not classroom or int(classroom.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=404, detail="Classroom not found")

    students_data = _build_export_students(db=db, classroom_id=int(classroom_id))
    content = generate_class_report_excel(
        classroom_data={"id": int(classroom.id), "name": str(classroom.name or f"#{classroom_id}")},
        students_data=students_data,
    )
    headers = {
        "Content-Disposition": f'attachment; filename="classroom_{classroom_id}_report.xlsx"',
    }
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )




@router.get("/teacher/classroom/{classroom_id}/student-reports")
def teacher_classroom_student_reports(
    request: Request,
    classroom_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    classroom = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    if not classroom or int(classroom.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=404, detail="Classroom not found")

    member_ids = [
        int(row[0])
        for row in db.query(ClassroomStudent.student_id)
        .filter(ClassroomStudent.classroom_id == int(classroom_id))
        .all()
    ]
    if not member_ids:
        return {"request_id": getattr(request.state, "request_id", "n/a"), "data": {"classroom_id": int(classroom_id), "reports": []}, "error": None}

    rows = (
        db.query(Notification)
        .filter(Notification.student_id.in_(member_ids), Notification.type == "student_final_report")
        .order_by(Notification.created_at.desc())
        .all()
    )

    reports = []
    for row in rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        if int(payload.get("classroom_id") or classroom_id) != int(classroom_id):
            continue
        reports.append(
            {
                "id": int(row.id),
                "title": row.title,
                "message": row.message,
                "student_id": int(row.student_id),
                "quiz_id": int(row.quiz_id),
                "is_read": bool(row.is_read),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "payload": payload,
            }
        )

    return {
        "request_id": getattr(request.state, "request_id", "n/a"),
        "data": {"classroom_id": int(classroom_id), "reports": reports},
        "error": None,
    }

@router.get("/teacher/classrooms/{classroom_id}/dashboard")
def classroom_dashboard(
    request: Request,
    classroom_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    c = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    if not c or int(c.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=404, detail="Classroom not found")

    members = db.query(ClassroomStudent).filter(ClassroomStudent.classroom_id == int(c.id)).all()
    student_ids = [int(m.user_id) for m in members]

    students: List[StudentProgressRow] = []
    if student_ids:
        urows = db.query(User).filter(User.id.in_(student_ids)).all()
        umap = {int(u.id): u for u in urows}

        for uid in student_ids:
            u = umap.get(int(uid))
            # latest plan for this classroom
            plan = (
                db.query(LearningPlan)
                .filter(LearningPlan.user_id == int(uid), LearningPlan.classroom_id == int(c.id))
                .order_by(LearningPlan.created_at.desc())
                .first()
            )

            tasks_total = 0
            tasks_done = 0
            hw_avg = None
            hw_last = None
            latest_plan_id = None
            assigned_topic = None

            if plan:
                latest_plan_id = int(plan.id)
                assigned_topic = plan.assigned_topic
                tasks_total = _compute_tasks_total(plan.plan_json or {})
                tasks_done = (
                    db.query(func.count(LearningPlanTaskCompletion.id))
                    .filter(
                        LearningPlanTaskCompletion.plan_id == int(plan.id),
                        LearningPlanTaskCompletion.completed == True,  # noqa: E712
                    )
                    .scalar()
                )
                tasks_done = int(tasks_done or 0)
                hw_avg, hw_last = _homework_stats(db, int(plan.id), int(uid))

            students.append(
                StudentProgressRow(
                    user_id=int(uid),
                    full_name=getattr(u, "full_name", None) if u else None,
                    tasks_done=int(tasks_done),
                    tasks_total=int(tasks_total),
                    homework_avg=hw_avg,
                    last_homework_score=hw_last,
                    latest_plan_id=latest_plan_id,
                    assigned_topic=assigned_topic,
                )
            )

    payload = ClassroomDashboardOut(classroom=_classroom_out(db, c), students=students).model_dump()
    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": payload, "error": None}


@router.post("/teacher/classrooms/{classroom_id}/assign-learning-plan")
def assign_learning_plan_to_classroom(
    request: Request,
    classroom_id: int,
    payload: AssignLearningPlanRequest,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    c = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    if not c or int(c.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=404, detail="Classroom not found")

    members = db.query(ClassroomStudent).filter(ClassroomStudent.classroom_id == int(c.id)).all()
    student_ids = [int(m.user_id) for m in members]
    if not student_ids:
        raise HTTPException(status_code=400, detail="Classroom has no students")

    # Build ONE plan and reuse for all students (plan_json has no user-specific fields)
    teacher_plan = build_teacher_learning_plan(
        db,
        user_id=int(teacher.id),
        teacher_id=int(teacher.id),
        level=str(payload.level or "beginner"),
        assigned_topic=payload.assigned_topic,
        modules=[],
        days=int(payload.days_total or 7),
        minutes_per_day=int(payload.minutes_per_day or 35),
    )

    created: List[Dict[str, int]] = []
    for uid in student_ids:
        # ensure user exists
        ensure_user_exists(db, int(uid), role="student")
        row = save_teacher_plan(
            db,
            user_id=int(uid),
            teacher_id=int(teacher.id),
            classroom_id=int(c.id),
            assigned_topic=payload.assigned_topic,
            level=str(payload.level or "beginner"),
            days_total=int(payload.days_total or 7),
            minutes_per_day=int(payload.minutes_per_day or 35),
            teacher_plan=teacher_plan.model_dump(),
        )
        created.append({"user_id": int(uid), "plan_id": int(row.id)})

    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": {"created": created}, "error": None}


@router.get("/classrooms/{classroom_id}/reports/latest")
def get_latest_class_report(
    request: Request,
    classroom_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    c = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    if not c or int(c.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=404, detail="Classroom not found")

    row = (
        db.query(ClassReport)
        .filter(ClassReport.classroom_id == int(classroom_id))
        .order_by(ClassReport.created_at.desc())
        .first()
    )
    if not row:
        return {"request_id": getattr(request.state, "request_id", "n/a"), "data": None, "error": None}

    payload = {
        "id": int(row.id),
        "classroom_id": int(row.classroom_id),
        "assessment_id": int(row.assessment_id),
        "narrative": row.narrative or "",
        "stats": row.stats_json or {},
        "improvement": row.improvement_json or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": payload, "error": None}


@router.get("/classrooms/{classroom_id}/reports/{report_id}")
def get_class_report_detail(
    request: Request,
    classroom_id: int,
    report_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    c = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    if not c or int(c.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=404, detail="Classroom not found")

    row = (
        db.query(ClassReport)
        .filter(ClassReport.id == int(report_id), ClassReport.classroom_id == int(classroom_id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    payload = {
        "id": int(row.id),
        "classroom_id": int(row.classroom_id),
        "assessment_id": int(row.assessment_id),
        "narrative": row.narrative or "",
        "stats": row.stats_json or {},
        "improvement": row.improvement_json or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": payload, "error": None}


@router.get("/classrooms/{classroom_id}/reports/latest/export")
def export_latest_classroom_report(
    classroom_id: int,
    format: str = Query("pdf"),
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    classroom = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    if not classroom or int(classroom.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=404, detail="Classroom not found")

    report_data = _build_latest_report_data(db=db, classroom_id=int(classroom_id))
    export_format = str(format or "pdf").strip().lower()
    class_name = str(classroom.name or f"#{classroom_id}")
    teacher_name = str(getattr(teacher, "full_name", None) or getattr(teacher, "email", None) or f"Teacher {teacher.id}")

    if export_format == "pdf":
        out_path = make_export_path(classroom_id=int(classroom_id), extension="pdf")
        export_class_report_pdf(report_data, out_path, class_name=class_name, teacher_name=teacher_name)
        return FileResponse(out_path, media_type="application/pdf", filename=f"classroom_{classroom_id}_latest_report.pdf")

    if export_format == "docx":
        out_path = make_export_path(classroom_id=int(classroom_id), extension="docx")
        export_class_report_docx(report_data, out_path, class_name=class_name, teacher_name=teacher_name)
        return FileResponse(
            out_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"classroom_{classroom_id}_latest_report.docx",
        )

    raise HTTPException(status_code=400, detail="format must be pdf or docx")
@router.post("/classrooms/{classroom_id}/entry-test")
def create_classroom_entry_test(
    request: Request,
    classroom_id: int,
    payload: ClassroomEntryTestCreateRequest,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    c = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    if not c or int(c.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=404, detail="Classroom not found")

    row = (
        db.query(ClassReport)
        .filter(ClassReport.id == int(report_id), ClassReport.classroom_id == int(classroom_id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    payload = {
        "id": int(row.id),
        "classroom_id": int(row.classroom_id),
        "assessment_id": int(row.assessment_id),
        "narrative": row.narrative or "",
        "stats": row.stats_json or {},
        "improvement": row.improvement_json or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": payload, "error": None}


@router.get("/classrooms/{classroom_id}/reports/{report_id}/export/excel")
def export_class_report_excel(
    classroom_id: int,
    report_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    c = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    if not c or int(c.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=404, detail="Classroom not found")

    row = (
        db.query(ClassReport)
        .filter(ClassReport.id == int(report_id), ClassReport.classroom_id == int(classroom_id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["student_id", "entry_score", "final_score", "delta"])
    for r in (row.improvement_json or {}).get("students", []):
        writer.writerow([r.get("student_id"), r.get("entry_score"), r.get("final_score"), r.get("delta")])

    mem = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    headers = {"Content-Disposition": f"attachment; filename=class_report_{report_id}.csv"}
    return StreamingResponse(mem, media_type="text/csv", headers=headers)
    if int(payload.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=400, detail="teacher_id mismatch")

    topic_ids = [int(tid) for tid in (payload.topic_ids or []) if int(tid) > 0]
    if not topic_ids:
        raise HTTPException(status_code=400, detail="topic_ids is required")

    topics = [
        str(r[0])
        for r in db.query(DocumentTopic.title)
        .filter(DocumentTopic.id.in_(topic_ids))
        .all()
        if r and r[0]
    ]
    if not topics:
        raise HTTPException(status_code=400, detail="No valid topics found")

    total_questions = max(1, int(payload.total_questions or 30))
    d = payload.distribution
    easy_count = int(total_questions * int(d.easy_pct) // 100)
    medium_count = int(total_questions * int(d.medium_pct) // 100)
    hard_count = int(total_questions - easy_count - medium_count)

    try:
        data = generate_assessment(
            db,
            teacher_id=int(teacher.id),
            classroom_id=int(classroom_id),
            title=str(payload.title or "Entry Test"),
            level="intermediate",
            kind="entry_test",
            easy_count=easy_count,
            medium_count=medium_count,
            hard_count=hard_count,
            document_ids=[int(x) for x in (payload.document_ids or [])],
            topics=topics,
            time_limit_minutes=int(payload.time_limit_minutes or 45),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    assessment_id = int(data.get("assessment_id") or 0)
    return {
        "request_id": getattr(request.state, "request_id", "n/a"),
        "data": {
            "assessment_id": assessment_id,
            "preview_url": f"/assessments/{assessment_id}",
        },
        "error": None,
    }

class AddStudentIn(BaseModel):
    email: str
    role: str = "student"


class AssignTopicsIn(BaseModel):
    topic_ids: list[int] = Field(default_factory=list)


class AssignExamIn(BaseModel):
    topic_ids: list[int] = Field(default_factory=list)
    document_ids: list[int] = Field(default_factory=list)
    title: str = "Assessment"
    duration_minutes: int = 45


def _ensure_teacher_classroom(db: Session, classroom_id: int, teacher_id: int) -> Classroom:
    c = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    if not c or int(c.teacher_id) != int(teacher_id):
        raise HTTPException(status_code=404, detail="Classroom not found")
    return c


@router.post('/classrooms')
def create_classroom_v2(request: Request, payload: ClassroomCreateRequest, db: Session = Depends(get_db), teacher: User = Depends(require_teacher)):
    return create_classroom(request=request, payload=payload, db=db, teacher=teacher)


@router.get('/classrooms/{classroom_id}/students')
def list_classroom_students(request: Request, classroom_id: int, db: Session = Depends(get_db), teacher: User = Depends(require_teacher)):
    _ensure_teacher_classroom(db, int(classroom_id), int(teacher.id))
    rows = (
        db.query(User.id, User.email, User.full_name, User.role)
        .join(ClassroomStudent, ClassroomStudent.student_id == User.id)
        .filter(ClassroomStudent.classroom_id == int(classroom_id))
        .order_by(User.full_name.asc(), User.id.asc())
        .all()
    )
    data = [
        {"id": int(r[0]), "email": str(r[1] or ''), "full_name": str(r[2] or ''), "role": str(r[3] or '')}
        for r in rows
    ]
    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": data, "error": None}


@router.post('/classrooms/{classroom_id}/students')
def add_classroom_student(request: Request, classroom_id: int, payload: AddStudentIn, db: Session = Depends(get_db), teacher: User = Depends(require_teacher)):
    _ensure_teacher_classroom(db, int(classroom_id), int(teacher.id))
    role = str(payload.role or 'student').strip().lower()
    user = db.query(User).filter(User.email == str(payload.email).strip().lower(), User.role == role).first()
    if not user:
        raise HTTPException(status_code=404, detail='Student not found by email + role')
    existing = db.query(ClassroomStudent).filter(ClassroomStudent.classroom_id == int(classroom_id), ClassroomStudent.student_id == int(user.id)).first()
    if not existing:
        db.add(ClassroomStudent(classroom_id=int(classroom_id), user_id=int(user.id)))
        db.commit()
    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": {"classroom_id": int(classroom_id), "student_id": int(user.id)}, "error": None}


@router.delete('/classrooms/{classroom_id}/students/{student_id}')
def remove_classroom_student(request: Request, classroom_id: int, student_id: int, db: Session = Depends(get_db), teacher: User = Depends(require_teacher)):
    _ensure_teacher_classroom(db, int(classroom_id), int(teacher.id))
    row = db.query(ClassroomStudent).filter(ClassroomStudent.classroom_id == int(classroom_id), ClassroomStudent.student_id == int(student_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail='Student not in classroom')
    db.delete(row)
    db.commit()
    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": {"removed": True}, "error": None}


@router.post('/classrooms/{classroom_id}/assign-topics')
def assign_topics_to_classroom(request: Request, classroom_id: int, payload: AssignTopicsIn, db: Session = Depends(get_db), teacher: User = Depends(require_teacher)):
    _ensure_teacher_classroom(db, int(classroom_id), int(teacher.id))
    topic_ids = [int(x) for x in (payload.topic_ids or []) if int(x) > 0]
    if not topic_ids:
        raise HTTPException(status_code=400, detail='topic_ids is required')

    topic_rows = db.query(DocumentTopic.id, DocumentTopic.document_id, DocumentTopic.title).filter(DocumentTopic.id.in_(topic_ids)).all()
    member_rows = db.query(ClassroomStudent.student_id).filter(ClassroomStudent.classroom_id == int(classroom_id)).all()
    student_ids = [int(r[0]) for r in member_rows]

    created = 0
    for sid in student_ids:
        for tid, doc_id, title in topic_rows:
            db.add(StudentAssignment(
                student_id=int(sid),
                classroom_id=int(classroom_id),
                topic_id=int(tid),
                document_id=int(doc_id),
                assignment_type='reading',
                student_level='trung_binh',
                status='pending',
                content_json={'topic_title': str(title or ''), 'source': 'classroom_assign_topics'},
            ))
            created += 1
    db.commit()
    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": {"assigned_count": created}, "error": None}


def _assign_exam_for_classroom(*, request: Request, db: Session, classroom_id: int, teacher: User, payload: AssignExamIn, kind: str):
    _ensure_teacher_classroom(db, int(classroom_id), int(teacher.id))
    topics = [
        str(r[0]) for r in db.query(DocumentTopic.title).filter(DocumentTopic.id.in_([int(x) for x in (payload.topic_ids or [])])).all() if r and r[0]
    ]
    if not topics:
        raise HTTPException(status_code=400, detail='No valid topics found')
    data = generate_assessment(
        db,
        teacher_id=int(teacher.id),
        classroom_id=int(classroom_id),
        title=str(payload.title or ('Placement Test' if kind == 'diagnostic_pre' else 'Final Test')),
        level='intermediate',
        kind=kind,
        easy_count=4,
        medium_count=4,
        hard_count=2,
        document_ids=[int(x) for x in (payload.document_ids or [])],
        topics=topics,
        time_limit_minutes=int(payload.duration_minutes or 45),
    )
    aid = int(data.get('assessment_id') or data.get('quiz_id') or 0)
    if aid > 0:
        ex = db.query(ClassroomAssessment).filter(ClassroomAssessment.classroom_id == int(classroom_id), ClassroomAssessment.assessment_id == aid).first()
        if not ex:
            db.add(ClassroomAssessment(classroom_id=int(classroom_id), assessment_id=aid, kind=kind, visible_to_students=True))
            db.commit()
    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": {"assessment_id": aid, "kind": kind}, "error": None}


@router.post('/classrooms/{classroom_id}/assign-placement')
def assign_placement(request: Request, classroom_id: int, payload: AssignExamIn, db: Session = Depends(get_db), teacher: User = Depends(require_teacher)):
    return _assign_exam_for_classroom(request=request, db=db, classroom_id=int(classroom_id), teacher=teacher, payload=payload, kind='diagnostic_pre')


@router.post('/classrooms/{classroom_id}/assign-final')
def assign_final(request: Request, classroom_id: int, payload: AssignExamIn, db: Session = Depends(get_db), teacher: User = Depends(require_teacher)):
    return _assign_exam_for_classroom(request=request, db=db, classroom_id=int(classroom_id), teacher=teacher, payload=payload, kind='diagnostic_post')


@router.get('/classrooms/{classroom_id}/leaderboard')
def classroom_leaderboard(request: Request, classroom_id: int, db: Session = Depends(get_db), teacher: User = Depends(require_teacher)):
    _ensure_teacher_classroom(db, int(classroom_id), int(teacher.id))
    student_rows = db.query(ClassroomStudent.student_id).filter(ClassroomStudent.classroom_id == int(classroom_id)).all()
    student_ids = [int(r[0]) for r in student_rows]
    data = []
    for sid in student_ids:
        user = db.query(User).filter(User.id == sid).first()
        attempts = db.query(Attempt).join(QuizSet, QuizSet.id == Attempt.quiz_set_id).filter(Attempt.user_id == sid).order_by(Attempt.created_at.desc()).all()
        final = next((a for a in attempts if str(getattr(db.query(QuizSet).filter(QuizSet.id == int(a.quiz_set_id)).first(), 'kind', '')).lower() in {'diagnostic_post','final_exam','final'}), None)
        score = float(getattr(final, 'score_percent', 0) or 0)
        level = classify_student_level(int(round(score)))
        data.append({'student_id': sid, 'student_name': str(getattr(user,'full_name','') or f'User #{sid}'), 'score': round(score,1), 'level': str(level.get('label_en') or 'Beginner')})
    data.sort(key=lambda x: x['score'], reverse=True)
    for i, row in enumerate(data, start=1):
        row['rank'] = i
    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": data, "error": None}


@router.delete('/teacher/classrooms/{classroom_id}')
def delete_teacher_classroom(request: Request, classroom_id: int, db: Session = Depends(get_db), teacher: User = Depends(require_teacher)):
    c = _ensure_teacher_classroom(db, int(classroom_id), int(teacher.id))
    db.query(ClassroomStudent).filter(ClassroomStudent.classroom_id == int(c.id)).delete(synchronize_session=False)
    db.delete(c)
    db.commit()
    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": {"deleted": True}, "error": None}


@router.get('/teacher/classrooms/{classroom_id}/students')
def list_teacher_classroom_students(
    request: Request,
    classroom_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    _ensure_teacher_classroom(db, int(classroom_id), int(teacher.id))
    q = (
        db.query(ClassroomStudent, User)
        .join(User, User.id == ClassroomStudent.student_id)
        .filter(ClassroomStudent.classroom_id == int(classroom_id))
    )
    total = q.count()
    rows = q.order_by(User.full_name.asc(), User.id.asc()).offset((page - 1) * page_size).limit(page_size).all()
    items = []
    for cs, u in rows:
        items.append({
            "id": int(u.id),
            "full_name": str(u.full_name or ''),
            "email": str(u.email or ''),
            "joined_at": cs.joined_at,
            "placement_score": cs.placement_score,
            "final_score": cs.final_score,
            "level": cs.level,
        })
    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": {"items": items, "pagination": {"page": page, "page_size": page_size, "total": total}}, "error": None}


@router.get('/student/classrooms/{classroom_id}/subjects')
def student_classroom_subjects(request: Request, classroom_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    c = db.query(Classroom).filter(Classroom.id == int(classroom_id), Classroom.is_active.is_(True)).first()
    if not c:
        raise HTTPException(status_code=404, detail='Classroom not found')
    member = db.query(ClassroomStudent).filter(ClassroomStudent.classroom_id == int(classroom_id), ClassroomStudent.student_id == int(user.id)).first()
    if not member and str(getattr(user, 'role', '')).lower() != 'teacher':
        raise HTTPException(status_code=403, detail='Not a classroom member')
    if not c.course_id:
        return {"request_id": getattr(request.state, "request_id", "n/a"), "data": [], "error": None}
    from app.models.mvp import Topic

    topics = db.query(Topic).filter(Topic.course_id == int(c.course_id)).order_by(Topic.id.asc()).all()
    data = [{"id": int(t.id), "title": str(t.title), "summary": str(t.summary or '')} for t in topics]
    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": data, "error": None}


@router.delete('/teacher/classrooms/{classroom_id}/students/{student_id}')
def remove_teacher_student(request: Request, classroom_id: int, student_id: int, db: Session = Depends(get_db), teacher: User = Depends(require_teacher)):
    _ensure_teacher_classroom(db, int(classroom_id), int(teacher.id))
    row = db.query(ClassroomStudent).filter(ClassroomStudent.classroom_id == int(classroom_id), ClassroomStudent.student_id == int(student_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail='Student not in classroom')
    db.delete(row)
    db.commit()
    return {"request_id": getattr(request.state, "request_id", "n/a"), "data": {"removed": True}, "error": None}


@router.post("/classrooms/join")
def join_classroom_legacy(
    request: Request,
    payload: ClassroomJoinRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    return join_classroom(request=request, payload=payload, db=db, user=user)


@router.get("/classrooms")
def list_my_classrooms_legacy(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    return list_my_classrooms(request=request, page=page, page_size=page_size, db=db, user=user)
