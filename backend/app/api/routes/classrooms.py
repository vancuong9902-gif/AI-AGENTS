from __future__ import annotations

import random
import string
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_teacher, require_user
from app.models.attempt import Attempt
from app.models.classroom import Classroom, ClassroomMember
from app.models.classroom_assessment import ClassroomAssessment
from app.models.learning_plan import LearningPlan, LearningPlanHomeworkSubmission, LearningPlanTaskCompletion
from app.models.quiz_set import QuizSet
from app.models.user import User
from app.schemas.classrooms import (
    AssignLearningPlanRequest,
    ClassroomCreateRequest,
    ClassroomDashboardOut,
    ClassroomJoinRequest,
    ClassroomOut,
    StudentProgressRow,
)
from app.services.learning_plan_service import build_teacher_learning_plan
from app.services.learning_plan_storage_service import save_teacher_plan
from app.services.lms_service import analyze_topic_weak_points, classify_student_level, generate_class_narrative, resolve_student_name, score_breakdown
from app.services.report_exporter import export_class_report_docx, export_class_report_pdf, make_export_path
from app.services.user_service import ensure_user_exists


router = APIRouter(tags=["classrooms"])


def _mk_join_code(length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(int(length)))


def _classroom_out(db: Session, c: Classroom) -> ClassroomOut:
    cnt = (
        db.query(func.count(ClassroomMember.id))
        .filter(ClassroomMember.classroom_id == int(c.id))
        .scalar()
    )
    return ClassroomOut(
        id=int(c.id),
        name=str(c.name),
        join_code=str(c.join_code),
        teacher_id=int(c.teacher_id),
        student_count=int(cnt or 0),
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
        code = _mk_join_code(6)
        if not db.query(Classroom).filter(Classroom.join_code == code).first():
            break
    else:
        raise HTTPException(status_code=500, detail="Failed to generate join code")

    row = Classroom(teacher_id=int(teacher.id), name=payload.name.strip(), join_code=code)
    db.add(row)
    db.commit()
    db.refresh(row)

    out = _classroom_out(db, row).model_dump()
    return {"request_id": request.state.request_id, "data": out, "error": None}


@router.get("/teacher/classrooms")
def list_teacher_classrooms(
    request: Request,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    rows = db.query(Classroom).filter(Classroom.teacher_id == int(teacher.id)).order_by(Classroom.created_at.desc()).all()
    out = [_classroom_out(db, c).model_dump() for c in rows]
    return {"request_id": request.state.request_id, "data": out, "error": None}


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
    return {"request_id": request.state.request_id, "data": out, "error": None}


@router.post("/classrooms/join")
def join_classroom(
    request: Request,
    payload: ClassroomJoinRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    code = payload.join_code.strip().upper()
    c = db.query(Classroom).filter(Classroom.join_code == code).first()
    if not c:
        raise HTTPException(status_code=404, detail="Invalid join code")

    # Ensure this demo user exists and is student-like
    ensure_user_exists(db, int(user.id), role=getattr(user, "role", "student") or "student")

    existing = (
        db.query(ClassroomMember)
        .filter(ClassroomMember.classroom_id == int(c.id), ClassroomMember.user_id == int(user.id))
        .first()
    )
    if not existing:
        db.add(ClassroomMember(classroom_id=int(c.id), user_id=int(user.id)))
        db.commit()

    out = _classroom_out(db, c).model_dump()
    return {"request_id": request.state.request_id, "data": out, "error": None}


@router.get("/classrooms")
def list_my_classrooms(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    # All classrooms where user is a member
    ids = db.query(ClassroomMember.classroom_id).filter(ClassroomMember.user_id == int(user.id)).all()
    cids = [int(x[0]) for x in ids if x and x[0] is not None]
    if not cids:
        return {"request_id": request.state.request_id, "data": [], "error": None}
    rows = db.query(Classroom).filter(Classroom.id.in_(cids)).order_by(Classroom.created_at.desc()).all()
    out = [_classroom_out(db, c).model_dump() for c in rows]
    return {"request_id": request.state.request_id, "data": out, "error": None}


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

    members = db.query(ClassroomMember).filter(ClassroomMember.classroom_id == int(classroom_id)).all()
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
        level_dist[level] = int(level_dist.get(level, 0)) + 1
        deltas.append(delta)
        if delta > 0:
            improved_count += 1
        students.append(
            {
                "name": resolve_student_name(uid, db),
                "entry_score": entry,
                "final_score": final,
                "level": level,
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

    members = db.query(ClassroomMember).filter(ClassroomMember.classroom_id == int(c.id)).all()
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
    return {"request_id": request.state.request_id, "data": payload, "error": None}


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

    members = db.query(ClassroomMember).filter(ClassroomMember.classroom_id == int(c.id)).all()
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

    return {"request_id": request.state.request_id, "data": {"created": created}, "error": None}


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
