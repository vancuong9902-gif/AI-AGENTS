from __future__ import annotations

import asyncio
import json
import logging
import re
import tempfile
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional
from app.db.session import get_db
from app.models.attempt import Attempt
from app.models.classroom import Classroom, ClassroomMember
from app.models.classroom import ClassroomMember
from app.models.classroom_assessment import ClassroomAssessment
from app.mas.base import AgentContext
from app.mas.contracts import Event
from app.mas.orchestrator import Orchestrator
from app.models.document_topic import DocumentTopic
from app.models.quiz_set import QuizSet
from app.models.question import Question
from app.models.learner_profile import LearnerProfile
from app.infra.queue import enqueue
from app.services.teacher_report_export_service import build_classroom_report_pdf
from app.services.analytics_service import build_classroom_final_report, export_classroom_final_report_pdf
from app.tasks.report_tasks import task_export_teacher_report_pdf
from app.services.lms_report_export_service import export_report_pdf, export_report_xlsx
from app.services.export_xlsx_service import export_classroom_gradebook_xlsx
from app.models.session import Session as UserSession
from app.models.student_assignment import StudentAssignment
from app.models.diagnostic_attempt import DiagnosticAttempt
from app.models.learning_plan import LearningPlan, LearningPlanHomeworkSubmission, LearningPlanTaskCompletion
from app.models.notification import Notification
from app.models.user import User
from app.services.assessment_service import generate_assessment, submit_assessment
from app.services.notification_service import notify_teacher_student_finished
from app.services.llm_service import chat_text, llm_available
from app.services.lms_service import (
    per_student_bloom_analysis,
    analyze_topic_weak_points,
    build_recommendations,
    classify_student_level,

    classify_student_multidim,
    generate_class_narrative,
    persist_multidim_profile,
    generate_student_evaluation_report,
    per_student_bloom_analysis,
    get_student_progress_comparison,
    get_student_homework_results,
    resolve_student_name,
    score_breakdown,
    _difficulty_from_breakdown_item,
    assign_topic_materials,
    assign_learning_path,
    teacher_report as build_teacher_report,
    generate_full_teacher_report,
)


router = APIRouter(tags=["lms"])
_report_cache: dict[int, dict] = {}
_report_cache_time: dict[int, float] = {}

_templates = Environment(
    loader=FileSystemLoader(str(Path(__file__).resolve().parents[2] / "templates")),
    autoescape=select_autoescape(["html", "xml"]),
)

_FINAL_EXAM_JOBS: dict[str, dict] = {}


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
    duration_seconds: int = 1800


class SubmitAttemptIn(BaseModel):
    user_id: int
    duration_sec: int = 0
    answers: list[dict] = Field(default_factory=list)


class PlacementQuizIn(BaseModel):
    topic_ids: list[int] = Field(default_factory=list)
    difficulty_settings: dict[str, int] = Field(
        default_factory=lambda: {"easy": 4, "medium": 4, "hard": 2})
    duration_seconds: int = 1800
    teacher_id: int = 1
    classroom_id: int = 1


class StartAttemptIn(BaseModel):
    quiz_id: int
    student_id: int


class SubmitAttemptByIdIn(BaseModel):
    answers: list[dict] = Field(default_factory=list)


class AttemptHeartbeatIn(BaseModel):
    answers: list[dict] = Field(default_factory=list)

class HeartbeatAttemptIn(BaseModel):
    answers: list[dict] = Field(default_factory=list)
def _attempt_status_payload(*, started: UserSession, duration_seconds: int) -> dict:
    now = datetime.now(timezone.utc)
    started_at = started.started_at or now
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)

    deadline = started_at
    if int(duration_seconds or 0) > 0:
        deadline = started_at + timedelta(seconds=int(duration_seconds))

    remaining_seconds = max(0, int((deadline - now).total_seconds())) if int(duration_seconds or 0) > 0 else None

    return {
        "attempt_id": int(started.id),
        "quiz_id": int(str(started.type).split(":", 1)[1]),
        "student_id": int(started.user_id),
        "start_time": started_at.isoformat(),
        "duration_seconds": int(duration_seconds or 0),
        "deadline": deadline.isoformat(),
        "server_time": now.isoformat(),
        "remaining_seconds": remaining_seconds,
        "timed_out": bool(remaining_seconds is not None and remaining_seconds <= 0),
    }

def _normalize_synced_diagnostic(base: dict) -> dict:
    """Ensure submit responses expose synced diagnostic payload consistently."""
    synced = dict(base.get("synced_diagnostic") or {})
    if not synced:
        return base

    plan_id = synced.get("plan_id") or synced.get("learning_plan_id") or base.get("learning_plan_id")
    if plan_id is not None:
        synced["plan_id"] = plan_id
        synced["learning_plan_id"] = plan_id

    if synced.get("stage") == "pre":
        if synced.get("level") is None and base.get("student_level") is not None:
            synced["level"] = base.get("student_level")

    base["synced_diagnostic"] = synced
    return base


class AssignPathIn(BaseModel):
    student_level: str
    document_ids: list[int] = Field(default_factory=list)
    classroom_id: int = 0


class AssignPathByQuizIn(BaseModel):
    user_id: int
    quiz_id: int
    classroom_id: int = 0


def _count_plan_tasks(plan_json: dict | None) -> tuple[int, int]:
    days = (plan_json or {}).get("days") if isinstance(plan_json, dict) else []
    if not isinstance(days, list):
        return 0, 0

    total = 0
    homework_total = 0
    for day in days:
        tasks = day.get("tasks") if isinstance(day, dict) else []
        if not isinstance(tasks, list):
            tasks = []
        for task in tasks:
            total += 1
            task_type = str((task or {}).get("type") or "").lower()
            if task_type == "homework":
                homework_total += 1
    return total, homework_total


def _normalize_submit_synced_diagnostic(base: dict, *, quiz_kind: str | None = None) -> dict:
    if not isinstance(base, dict):
        return base

    synced = base.get("synced_diagnostic")
    synced_payload = dict(synced) if isinstance(synced, dict) else {}

    plan_id = synced_payload.get("plan_id") or synced_payload.get("learning_plan_id")
    if plan_id is None:
        plan_id = base.get("learning_plan_id")
    if plan_id is None:
        assigned = base.get("assigned_learning_path")
        if isinstance(assigned, dict):
            plan_id = assigned.get("plan_id")

    level = synced_payload.get("level")
    if not level:
        student_level = base.get("student_level")
        if isinstance(student_level, dict):
            level = student_level.get("level_key") or student_level.get("label")
        elif isinstance(student_level, str):
            level = student_level

    stage = synced_payload.get("stage")
    normalized_kind = str(quiz_kind or base.get("assessment_kind") or "").lower()
    if not stage and normalized_kind == "diagnostic_pre":
        stage = "pre"

    if synced_payload or plan_id is not None or level or stage:
        if plan_id is not None:
            synced_payload["plan_id"] = plan_id
            synced_payload["learning_plan_id"] = plan_id
        if level:
            synced_payload["level"] = level
        if stage:
            synced_payload["stage"] = stage
        base["synced_diagnostic"] = synced_payload

    return base




def _extract_quiz_document_ids(quiz: QuizSet | None) -> list[int]:
    if not quiz:
        return []
    raw = getattr(quiz, "document_ids_json", None)
    if not raw:
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    out: list[int] = []
    for item in parsed:
        try:
            out.append(int(item))
        except Exception:
            continue
    return out


def _infer_document_ids_from_topics(db: Session, topic_names: list[str]) -> list[int]:
    names = [str(t).strip() for t in (topic_names or []) if str(t).strip()]
    if not names:
        return []

    doc_ids: set[int] = set()
    for topic_name in names:
        topic_row = (
            db.query(DocumentTopic.document_id)
            .filter(DocumentTopic.title.ilike(f"%{topic_name}%"))
            .order_by(DocumentTopic.topic_index.asc(), DocumentTopic.id.asc())
            .first()
        )
        if topic_row is None:
            continue
        row_val = topic_row[0] if isinstance(topic_row, tuple) else getattr(topic_row, "document_id", topic_row)
        try:
            doc_ids.add(int(row_val))
        except Exception:
            continue
    return sorted(doc_ids)


def _upsert_plan_weak_topics(db: Session, *, plan_id: int | None, weak_topics: list[str]) -> None:
    if not plan_id:
        return
    plan = db.query(LearningPlan).filter(LearningPlan.id == int(plan_id)).first()
    if not plan:
        return
    payload = dict(plan.plan_json or {}) if isinstance(plan.plan_json, dict) else {}
    payload["weak_topics"] = [str(t) for t in (weak_topics or []) if str(t).strip()]
    plan.plan_json = payload
    db.add(plan)
    db.commit()

def _final_exam_eligibility_payload(db: Session, *, classroom_id: int, user_id: int) -> dict:
    has_diagnostic_pre = (
        db.query(DiagnosticAttempt.id)
        .filter(
            DiagnosticAttempt.user_id == int(user_id),
            DiagnosticAttempt.stage == "pre",
            DiagnosticAttempt.attempt_id.isnot(None),
        )
        .first()
        is not None
    )

    latest_plan = (
        db.query(LearningPlan)
        .filter(
            LearningPlan.user_id == int(user_id),
            LearningPlan.classroom_id == int(classroom_id),
        )
        .order_by(LearningPlan.created_at.desc())
        .first()
    )

    if not latest_plan:
        latest_plan = (
            db.query(LearningPlan)
            .filter(LearningPlan.user_id == int(user_id))
            .order_by(LearningPlan.created_at.desc())
            .first()
        )

    learning_progress_pct = 0.0
    homework_progress_pct = 0.0
    completed_tasks = 0
    total_tasks = 0

    if latest_plan:
        total_tasks, total_homework_tasks = _count_plan_tasks(latest_plan.plan_json or {})
        done_rows = (
            db.query(LearningPlanTaskCompletion.day_index, LearningPlanTaskCompletion.task_index)
            .filter(
                LearningPlanTaskCompletion.plan_id == int(latest_plan.id),
                LearningPlanTaskCompletion.completed.is_(True),
            )
            .all()
        )
        completed_tasks = len({(int(r.day_index), int(r.task_index)) for r in done_rows})
        learning_progress_pct = round((completed_tasks / total_tasks) * 100, 1) if total_tasks > 0 else 0.0

        homework_done = (
            db.query(func.count(LearningPlanHomeworkSubmission.id))
            .filter(
                LearningPlanHomeworkSubmission.plan_id == int(latest_plan.id),
                LearningPlanHomeworkSubmission.user_id == int(user_id),
            )
            .scalar()
            or 0
        )
        if total_homework_tasks > 0:
            homework_progress_pct = round(min(1.0, float(homework_done) / float(total_homework_tasks)) * 100, 1)

    if homework_progress_pct == 0.0:
        assignment_total = (
            db.query(func.count(StudentAssignment.id))
            .filter(
                StudentAssignment.student_id == int(user_id),
                StudentAssignment.classroom_id == int(classroom_id),
                StudentAssignment.assignment_type.in_(["exercise", "quiz_practice", "essay_case_study"]),
            )
            .scalar()
            or 0
        )
        assignment_completed = (
            db.query(func.count(StudentAssignment.id))
            .filter(
                StudentAssignment.student_id == int(user_id),
                StudentAssignment.classroom_id == int(classroom_id),
                StudentAssignment.assignment_type.in_(["exercise", "quiz_practice", "essay_case_study"]),
                StudentAssignment.status == "completed",
            )
            .scalar()
            or 0
        )
        if assignment_total > 0:
            homework_progress_pct = round((assignment_completed / assignment_total) * 100, 1)

    conditions = [
        {
            "label": "Đã làm bài kiểm tra đầu vào",
            "met": bool(has_diagnostic_pre),
            "detail": "Đã hoàn thành" if has_diagnostic_pre else "Bạn cần hoàn thành bài kiểm tra đầu vào trước.",
        },
        {
            "label": "Hoàn thành 70% lộ trình học",
            "met": float(learning_progress_pct) >= 70.0,
            "progress_pct": float(learning_progress_pct),
            "detail": f"{completed_tasks}/{total_tasks} nhiệm vụ" if total_tasks > 0 else "Chưa có lộ trình học được giao.",
        },
        {
            "label": "Hoàn thành 80% bài tập",
            "met": float(homework_progress_pct) >= 80.0,
            "progress_pct": float(homework_progress_pct),
            "detail": "Tiến độ bài tập trong lớp hiện tại.",
        },
    ]

    blocking = next((cond["label"] for cond in conditions if not cond.get("met")), None)
    return {
        "is_eligible": blocking is None,
        "conditions": conditions,
        "blocking_condition": blocking,
    }


@router.get("/v1/lms/final-exam/eligibility")
def final_exam_eligibility(
    request: Request,
    classroomId: int = Query(...),
    userId: int = Query(...),
    db: Session = Depends(get_db),
):
    payload = _final_exam_eligibility_payload(db, classroom_id=int(classroomId), user_id=int(userId))
    return {"request_id": request.state.request_id, "data": payload, "error": None}


@router.post("/v1/lms/final-exam/generate")
def final_exam_generate_job(
    request: Request,
    classroomId: int = Query(...),
    userId: int = Query(...),
    db: Session = Depends(get_db),
):
    eligibility = _final_exam_eligibility_payload(db, classroom_id=int(classroomId), user_id=int(userId))
    if not eligibility["is_eligible"]:
        raise HTTPException(status_code=403, detail={"code": "PREREQUISITE_NOT_MET", **eligibility})

    topic_rows = db.query(DocumentTopic.id, func.coalesce(DocumentTopic.teacher_edited_title, DocumentTopic.title)).filter(DocumentTopic.status == "approved").all()
    topics = [str(r[1]) for r in topic_rows if r and r[1]]

    req = GenerateLmsQuizIn(
        teacher_id=1,
        classroom_id=int(classroomId),
        topics=topics,
        title="Final Test",
        easy_count=4,
        medium_count=4,
        hard_count=2,
    )
    exclude_ids = collect_excluded_quiz_ids_for_classroom_final(db, classroom_id=int(classroomId))
    response = _generate_assessment_lms(
        request=request,
        db=db,
        payload=req,
        kind="diagnostic_post",
        exclude_quiz_ids=exclude_ids,
        similarity_threshold=0.75,
    )
    data = response.get("data") or {}
    data["excluded_from_count"] = len(exclude_ids)

    quiz_id = int(data.get("assessment_id") or data.get("quiz_id") or 0)
    duration_seconds = 45 * 60
    if quiz_id > 0:
        quiz = db.query(QuizSet).filter(QuizSet.id == quiz_id).first()
        if quiz:
            duration_seconds = int(getattr(quiz, "duration_seconds", duration_seconds) or duration_seconds)

    job_id = str(uuid.uuid4())
    _FINAL_EXAM_JOBS[job_id] = {
        "started_at": time.time(),
        "status": "processing",
        "topics_count": len(set(topics)),
        "result": {
            "quiz_id": quiz_id,
            "assessment_id": quiz_id,
            "duration_seconds": int(duration_seconds),
            "questions": data.get("questions") or [],
            "topic_count": len(set(topics)),
            "difficulty": {
                "easy": int(req.easy_count),
                "medium": int(req.medium_count),
                "hard": int(req.hard_count),
            },
        },
    }
    return {"request_id": request.state.request_id, "data": {"jobId": job_id}, "error": None}


@router.get("/v1/lms/final-exam/status")
def final_exam_generate_status(request: Request, jobId: str = Query(...), db: Session = Depends(get_db)):
    _ = db  # keep dependency parity and future DB-based jobs.
    job = _FINAL_EXAM_JOBS.get(str(jobId))
    if not job:
        raise HTTPException(status_code=404, detail="Final exam generation job not found")

    elapsed = max(0.0, time.time() - float(job.get("started_at") or time.time()))
    progress = min(100, int((elapsed / 12.0) * 100))
    status = "completed" if progress >= 100 else "processing"
    job["status"] = status

    response = {
        "jobId": str(jobId),
        "status": status,
        "progress": progress,
        "topics_count": int(job.get("topics_count") or 0),
    }
    if status == "completed":
        response["result"] = job.get("result") or {}
    return {"request_id": request.state.request_id, "data": response, "error": None}


@router.post("/lms/teacher/select-topics")
def teacher_select_topics(request: Request, payload: TeacherTopicSelectionIn, db: Session = Depends(get_db)):
    if not payload.topics:
        raise HTTPException(
            status_code=400, detail="Vui lòng chọn ít nhất 1 topic")

    existing = {
        str(r[0]).strip().lower()
        for r in db.query(func.coalesce(DocumentTopic.teacher_edited_title, DocumentTopic.title)).filter(DocumentTopic.document_id == int(payload.document_id)).filter(DocumentTopic.status == "approved").all()
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


def parse_duration_seconds(level_text: str | None) -> int | None:
    raw = str(level_text or "").strip()
    if not raw:
        return None
    match = re.search(r"(?:^|;)\s*duration\s*=\s*(\d+)\s*(?:$|;)", raw, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        seconds = int(match.group(1))
    except Exception:
        return None
    return seconds if seconds > 0 else None


def _clean_level_text(level_text: str | None) -> str:
    raw = str(level_text or "")
    cleaned = re.sub(r"(?:^|;)\s*duration\s*=\s*\d+\s*(?=$|;)", "", raw, flags=re.IGNORECASE)
    cleaned = re.sub(r";{2,}", ";", cleaned).strip(" ;")
    return cleaned or raw


def _collect_quiz_ids_from_learning_plan_json(plan_json: dict | None) -> set[int]:
    if not isinstance(plan_json, dict):
        return set()

    found: set[int] = set()

    def _add_from_dict(d: dict) -> None:
        for key in ("quiz_set_id", "quiz_id", "assessment_id"):
            val = d.get(key)
            try:
                iv = int(val)
            except Exception:
                continue
            if iv > 0:
                found.add(iv)

    assigned_tasks = plan_json.get("assigned_tasks")
    if isinstance(assigned_tasks, list):
        for task in assigned_tasks:
            if isinstance(task, dict):
                _add_from_dict(task)

    days = plan_json.get("days")
    if isinstance(days, list):
        for day in days:
            if not isinstance(day, dict):
                continue
            tasks = day.get("tasks")
            if not isinstance(tasks, list):
                continue
            for task in tasks:
                if isinstance(task, dict):
                    _add_from_dict(task)
    return found


def collect_excluded_quiz_ids_for_classroom_final(db: Session, classroom_id: int) -> list[int]:
    cid = int(classroom_id)
    assigned_ids = {
        int(r[0])
        for r in (
            db.query(ClassroomAssessment.assessment_id)
            .filter(ClassroomAssessment.classroom_id == cid)
            .distinct()
            .all()
        )
        if r and r[0] is not None
    }

    placement_ids = {
        int(r[0])
        for r in (
            db.query(ClassroomAssessment.assessment_id)
            .join(QuizSet, QuizSet.id == ClassroomAssessment.assessment_id)
            .filter(
                ClassroomAssessment.classroom_id == cid,
                QuizSet.kind == "diagnostic_pre",
            )
            .distinct()
            .all()
        )
        if r and r[0] is not None
    }

    excluded = assigned_ids | placement_ids
    return sorted(excluded)


def build_classroom_final_exclude_quiz_ids(
    db: Session,
    *,
    classroom_id: int,
    current_quiz_id: int | None = None,
) -> list[int]:
    cid = int(classroom_id)
    placement_ids = {
        int(r[0])
        for r in (
            db.query(ClassroomAssessment.assessment_id)
            .join(QuizSet, QuizSet.id == ClassroomAssessment.assessment_id)
            .filter(
                ClassroomAssessment.classroom_id == cid,
                QuizSet.kind == "diagnostic_pre",
            )
            .distinct()
            .all()
        )
        if r and r[0] is not None
    }

    extra_exclude_ids = {
        int(r[0])
        for r in (
            db.query(ClassroomAssessment.assessment_id)
            .filter(ClassroomAssessment.classroom_id == cid)
            .distinct()
            .all()
        )
        if r and r[0] is not None
    }

    if current_quiz_id is not None:
        extra_exclude_ids.discard(int(current_quiz_id))

    return sorted(placement_ids | extra_exclude_ids)
    excluded: set[int] = set(_placement_quiz_ids_by_classroom(db, classroom_id=cid))

    assigned_ids = (
        db.query(ClassroomAssessment.assessment_id)
        .filter(ClassroomAssessment.classroom_id == cid)
        .distinct()
        .all()
    )
    excluded.update(int(r[0]) for r in assigned_ids if r and r[0] is not None)
    return sorted(excluded)


def _placement_quiz_ids_by_classroom(db: Session, *, classroom_id: int) -> list[int]:
    rows = (
        db.query(ClassroomAssessment.assessment_id)
        .join(QuizSet, QuizSet.id == ClassroomAssessment.assessment_id)
        .filter(
            ClassroomAssessment.classroom_id == int(classroom_id),
            QuizSet.kind == "diagnostic_pre",
        )
        .distinct()
        .all()
    )
    return [int(r[0]) for r in rows if r and r[0] is not None]


def _generate_assessment_lms(
    *,
    request: Request,
    db: Session,
    payload: GenerateLmsQuizIn,
    kind: str,
    exclude_quiz_ids: list[int] | None = None,
    similarity_threshold: float = 0.75,
):
    data = generate_assessment(
        db,
        teacher_id=int(payload.teacher_id),
        classroom_id=int(payload.classroom_id),
        title=payload.title,
        level="intermediate",
        kind=kind,
        easy_count=int(payload.easy_count),
        medium_count=int(payload.medium_count),
        hard_count=int(payload.hard_count),
        document_ids=[int(x) for x in payload.document_ids],
        topics=payload.topics,
        exclude_quiz_ids=exclude_quiz_ids,
        similarity_threshold=float(similarity_threshold),
    )
    quiz_id = int(data.get("quiz_id") or data.get("assessment_id") or 0)
    if quiz_id > 0:
        quiz = db.query(QuizSet).filter(QuizSet.id == quiz_id).first()
        if quiz:
            quiz.duration_seconds = int(payload.duration_seconds or 1800)
            db.add(quiz)
            db.commit()
    return {"request_id": request.state.request_id, "data": data, "error": None}


def _quiz_duration_map(quiz: QuizSet) -> int:
    try:
        duration = int(getattr(quiz, "duration_seconds", 0) or 0)
        if duration > 0:
            return duration

        parsed = parse_duration_seconds(getattr(quiz, "level", ""))
        if parsed and parsed > 0:
            return int(parsed)

        level = str(getattr(quiz, "level", "") or "").lower()
        if "hard" in level or "advanced" in level:
            return 2700
        if "easy" in level or "beginner" in level:
            return 1200
        return 1800
    except Exception:
        return 1800


def _attempt_timing(session: UserSession, duration_seconds: int) -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    started_at = session.started_at or now
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    elapsed_seconds = max(0, int((now - started_at).total_seconds()))
    time_left_seconds = max(0, int(duration_seconds or 0) - elapsed_seconds)
    return elapsed_seconds, time_left_seconds


def _lock_attempt_if_expired(session: UserSession, *, time_left_seconds: int) -> bool:
    now = datetime.now(timezone.utc)
    changed = False
    if time_left_seconds <= 0:
        if session.locked_at is None:
            session.locked_at = now
            changed = True
        if session.ended_at is None:
            session.ended_at = now
            changed = True
    return changed
def _attempt_quiz_id(session: UserSession) -> int:
    raw = str(getattr(session, "type", "") or "")
    if not raw.startswith("quiz_attempt:"):
        raise HTTPException(status_code=404, detail="Attempt not found")
    try:
        return int(raw.split(":", 1)[1])
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Attempt not found") from exc


def _normalize_started_at_utc(session: UserSession, now: datetime) -> datetime:
    started_at = session.started_at or now
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    return started_at


def _build_answer_list_from_questions(*, questions: list[Question], answers: list[dict]) -> list[dict]:
    by_qid: dict[int, dict] = {}
    for item in answers or []:
        if not isinstance(item, dict):
            continue
        try:
            qid = int(item.get("question_id"))
        except Exception:
            continue
        by_qid[qid] = item

    normalized: list[dict] = []
    for q in questions or []:
        src = by_qid.get(int(q.id), {})
        normalized.append(
            {
                "question_id": int(q.id),
                "answer_index": src.get("answer_index"),
                "answer_text": src.get("answer_text"),
            }
        )
    return normalized


def _publish_mas_event_non_blocking(db: Session, *, event: Event) -> None:
    """Phát event MAS theo cơ chế non-blocking để không ảnh hưởng luồng nộp bài."""

    def _runner() -> None:
        orchestrator = Orchestrator(db)
        ctx = AgentContext(user_id=int(event.user_id), document_ids=[])
        orchestrator.run(event, ctx)

    async def _async_runner() -> None:
        _runner()

    try:
        asyncio.ensure_future(_async_runner())
    except Exception:
        # Fallback an toàn nếu không có event loop khả dụng trong context hiện tại.
        pass


@router.post("/lms/placement/generate")
def lms_generate_placement(request: Request, payload: GenerateLmsQuizIn, db: Session = Depends(get_db)):
    payload.title = payload.title or "Placement Test"
    return _generate_assessment_lms(request=request, db=db, payload=payload, kind="diagnostic_pre")


@router.post("/lms/final/generate")
def lms_generate_final(request: Request, payload: GenerateLmsQuizIn, db: Session = Depends(get_db)):
    payload.title = payload.title or "Final Test"
    exclude_ids = build_classroom_final_exclude_quiz_ids(
        db,
        classroom_id=int(payload.classroom_id),
    )

    data = generate_assessment(
        db,
        teacher_id=int(payload.teacher_id),
        classroom_id=int(payload.classroom_id),
        title=payload.title,
        level="intermediate",
        kind="diagnostic_post",
        easy_count=int(payload.easy_count),
        medium_count=int(payload.medium_count),
        hard_count=int(payload.hard_count),
        document_ids=[int(x) for x in payload.document_ids],
        topics=payload.topics,
        exclude_quiz_ids=exclude_ids,
        similarity_threshold=0.75,
    )
    data["excluded_from_count"] = len(exclude_ids)
    return {"request_id": request.state.request_id, "data": data, "error": None}


@router.get("/lms/debug/quiz-overlap/{id1}/{id2}")
def debug_quiz_overlap(request: Request, id1: int, id2: int, db: Session = Depends(get_db)):
    from difflib import SequenceMatcher

    s1 = [str(r[0] or "") for r in db.query(Question.stem).filter(Question.quiz_set_id == id1).all()]
    s2 = [str(r[0] or "") for r in db.query(Question.stem).filter(Question.quiz_set_id == id2).all()]

    dups: list[dict[str, object]] = []
    for a in s1:
        for b in s2:
            ratio = SequenceMatcher(None, a.lower(), b.lower()).ratio()
            if ratio >= 0.75:
                dups.append({"s1": a[:80], "s2": b[:80], "sim": round(float(ratio), 3)})

    return {
        "request_id": request.state.request_id,
        "data": {
            "overlap_count": len(dups),
            "overlap_pct": round(len(dups) / max(1, len(s1)) * 100, 1),
            "quiz1_total": len(s1),
            "quiz2_total": len(s2),
            "samples": dups[:10],
        },
        "error": None,
    }


@router.post("/quizzes/placement")
def create_placement_quiz(request: Request, payload: PlacementQuizIn, db: Session = Depends(get_db)):
    topics = [
        str(r[0])
        for r in db.query(func.coalesce(DocumentTopic.teacher_edited_title, DocumentTopic.title))
        .filter(DocumentTopic.id.in_([int(tid) for tid in payload.topic_ids]))
        .filter(DocumentTopic.status == "approved")
        .all()
    ]
    req = GenerateLmsQuizIn(
        teacher_id=int(payload.teacher_id),
        classroom_id=int(payload.classroom_id),
        topics=topics,
        title="Placement Test",
        easy_count=int(payload.difficulty_settings.get("easy", 4)),
        medium_count=int(payload.difficulty_settings.get("medium", 4)),
        hard_count=int(payload.difficulty_settings.get("hard", 2)),
    )
    response = _generate_assessment_lms(
        request=request, db=db, payload=req, kind="diagnostic_pre")
    quiz_id = int((response.get("data") or {}).get("assessment_id") or 0)
    if quiz_id > 0:
        quiz = db.query(QuizSet).filter(QuizSet.id == quiz_id).first()
        if quiz:
            quiz.duration_seconds = int(payload.duration_seconds)
            db.commit()
    response["data"]["duration_seconds"] = int(payload.duration_seconds)
    response["data"]["quiz_type"] = "placement"
    return response


@router.post("/quizzes/final")
def create_final_quiz(request: Request, payload: PlacementQuizIn, db: Session = Depends(get_db)):
    topics = [
        str(r[0])
        for r in db.query(func.coalesce(DocumentTopic.teacher_edited_title, DocumentTopic.title))
        .filter(DocumentTopic.id.in_([int(tid) for tid in payload.topic_ids]))
        .filter(DocumentTopic.status == "approved")
        .all()
    ]
    req = GenerateLmsQuizIn(
        teacher_id=int(payload.teacher_id),
        classroom_id=int(payload.classroom_id),
        topics=topics,
        title="Final Test",
        easy_count=int(payload.difficulty_settings.get("easy", 4)),
        medium_count=int(payload.difficulty_settings.get("medium", 4)),
        hard_count=int(payload.difficulty_settings.get("hard", 2)),
    )
    exclude_ids = build_classroom_final_exclude_quiz_ids(
        db,
        classroom_id=int(payload.classroom_id),
    )
    response = _generate_assessment_lms(
        request=request,
        db=db,
        payload=req,
        kind="diagnostic_post",
        exclude_quiz_ids=exclude_ids,
        similarity_threshold=0.75,
    )
    quiz_id = int((response.get("data") or {}).get("assessment_id") or 0)
    if quiz_id > 0:
        quiz = db.query(QuizSet).filter(QuizSet.id == quiz_id).first()
        if quiz:
            quiz.duration_seconds = int(payload.duration_seconds)
            db.commit()
    response["data"]["duration_seconds"] = int(payload.duration_seconds)
    response["data"]["quiz_type"] = "final"
    response["data"]["excluded_from_count"] = len(exclude_ids)
    return response


@router.post("/attempts/start")
def start_attempt(request: Request, payload: StartAttemptIn, db: Session = Depends(get_db)):
    quiz_id = int(payload.quiz_id)
    student_id = int(payload.student_id)

    allowed = (
        db.query(ClassroomAssessment.id)
        .join(ClassroomMember, ClassroomMember.classroom_id == ClassroomAssessment.classroom_id)
        .filter(
            ClassroomMember.user_id == student_id,
            ClassroomAssessment.assessment_id == quiz_id,
        )
        .first()
    )
    if not allowed:
        raise HTTPException(status_code=404, detail="Attempt not found")

    session = UserSession(user_id=student_id, type=f"quiz_attempt:{quiz_id}")
    db.add(session)
    db.commit()
    db.refresh(session)

    quiz = db.query(QuizSet).filter(QuizSet.id == quiz_id).first()
    duration_seconds = _quiz_duration_map(quiz) if quiz else 0

    server_now = datetime.now(timezone.utc)
    started_at = _normalize_started_at_utc(session, server_now)
    deadline_utc = started_at
    if int(duration_seconds or 0) > 0:
        deadline_utc = started_at + timedelta(seconds=int(duration_seconds))

    return {
        "request_id": request.state.request_id,
        "data": {
            "attempt_id": int(session.id),
            "quiz_id": quiz_id,
            "student_id": student_id,
            "start_time": started_at.isoformat(),
            "duration_seconds": int(duration_seconds or 0),
            "server_now": server_now.isoformat(),
            "deadline_utc": deadline_utc.isoformat(),
        },
        "data": _attempt_status_payload(started=session, duration_seconds=int(duration_seconds or 0)),
        "error": None,
    }


@router.post("/attempts/{attempt_id}/heartbeat")
def heartbeat_attempt(request: Request, attempt_id: int, payload: AttemptHeartbeatIn, db: Session = Depends(get_db)):
    started = db.query(UserSession).filter(UserSession.id == int(attempt_id)).first()
    if not started or not str(started.type or "").startswith("quiz_attempt:"):
        raise HTTPException(status_code=404, detail="Attempt not found")

    quiz_id = int(str(started.type).split(":", 1)[1])
    quiz = db.query(QuizSet).filter(QuizSet.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    duration_seconds = _quiz_duration_map(quiz)
    elapsed_seconds, time_left_seconds = _attempt_timing(started, duration_seconds)

    _lock_attempt_if_expired(started, time_left_seconds=time_left_seconds)
    if started.locked_at is None:
        started.answers_snapshot_json = payload.answers or []
    started.last_heartbeat_at = datetime.now(timezone.utc)

    db.add(started)
    db.commit()
    db.refresh(started)

    return {
        "request_id": request.state.request_id,
        "data": {
            "elapsed_seconds": elapsed_seconds,
            "time_left_seconds": max(0, time_left_seconds),
            "locked": bool(started.locked_at),
        },
        "error": None,
    }


@router.get("/attempts/{attempt_id}/timer-status")
def get_attempt_timer_status(request: Request, attempt_id: int, db: Session = Depends(get_db)):
    started = db.query(UserSession).filter(UserSession.id == int(attempt_id)).first()
    if not started or not str(started.type or "").startswith("quiz_attempt:"):
        raise HTTPException(status_code=404, detail="Attempt not found")

    quiz_id = int(str(started.type).split(":", 1)[1])
    quiz = db.query(QuizSet).filter(QuizSet.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    duration_seconds = _quiz_duration_map(quiz)
    elapsed_seconds, time_left_seconds = _attempt_timing(started, duration_seconds)
    changed = _lock_attempt_if_expired(started, time_left_seconds=time_left_seconds)
    if changed:
        db.add(started)
        db.commit()
        db.refresh(started)
def heartbeat_attempt(request: Request, attempt_id: int, payload: HeartbeatAttemptIn, db: Session = Depends(get_db)):
    started = db.query(UserSession).filter(UserSession.id == int(attempt_id)).first()
    if not started:
        raise HTTPException(status_code=404, detail="Attempt not found")

    quiz_id = _attempt_quiz_id(started)
    quiz = db.query(QuizSet).filter(QuizSet.id == int(quiz_id)).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    now = datetime.now(timezone.utc)
    started_at = _normalize_started_at_utc(started, now)
    elapsed = max(0, int((now - started_at).total_seconds()))
    duration_seconds = int(_quiz_duration_map(quiz) or 0)

    locked = False
    if duration_seconds > 0 and elapsed >= duration_seconds:
        locked = True
        if started.locked_at is None:
            started.locked_at = now
        if started.ended_at is None:
            started.ended_at = now
    elif started.locked_at is not None:
        locked = True

    started.last_heartbeat_at = now
    if not locked:
        started.answers_snapshot_json = payload.answers or []

    db.add(started)
    db.commit()

    elapsed_seconds = max(0, int((now - started_at).total_seconds()))
    time_left_seconds = max(0, int(duration_seconds) - elapsed_seconds) if duration_seconds > 0 else 0

    return {
        "request_id": request.state.request_id,
        "data": {
            "server_now": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": elapsed_seconds,
            "remaining_seconds": max(0, time_left_seconds),
            "locked": bool(started.locked_at),
        },
        "error": None,
    }


@router.post("/attempts/{attempt_id}/submit")
def submit_attempt_by_id(request: Request, attempt_id: int, payload: SubmitAttemptByIdIn, db: Session = Depends(get_db)):
            "attempt_id": int(started.id),
            "server_now": now.isoformat(),
            "duration_seconds": int(duration_seconds),
            "elapsed_seconds": int(elapsed_seconds),
            "time_left_seconds": int(time_left_seconds),
            "locked": bool(locked),
        },

@router.get("/attempts/{attempt_id}/status")
def get_attempt_status(request: Request, attempt_id: int, db: Session = Depends(get_db)):
    started = db.query(UserSession).filter(
        UserSession.id == int(attempt_id)).first()
    if not started or not str(started.type or "").startswith("quiz_attempt:"):
        raise HTTPException(status_code=404, detail="Attempt not found")

    quiz_id = int(str(started.type).split(":", 1)[1])
    quiz = db.query(QuizSet).filter(QuizSet.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    duration_seconds = _quiz_duration_map(quiz)
    return {
        "request_id": request.state.request_id,
        "data": _attempt_status_payload(started=started, duration_seconds=int(duration_seconds or 0)),
        "error": None,
    }


@router.get("/attempts/{attempt_id}/result")
def get_attempt_result(request: Request, attempt_id: int, db: Session = Depends(get_db)):
    session = db.query(UserSession).filter(UserSession.id == int(attempt_id)).first()
    if not session or not str(session.type or "").startswith("quiz_attempt:"):
        raise HTTPException(status_code=404, detail="Attempt session not found")

    try:
        quiz_id = int(str(session.type).split(":", 1)[1])
    except Exception:
        raise HTTPException(status_code=400, detail="Attempt session payload is invalid")

    quiz = db.query(QuizSet).filter(QuizSet.id == int(quiz_id)).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    linked_attempt_record_id = getattr(session, "linked_attempt_record_id", None)
    attempt_record = None
    if linked_attempt_record_id is not None:
        attempt_record = db.query(Attempt).filter(Attempt.id == int(linked_attempt_record_id)).first()

    if not attempt_record:
        q = (
            db.query(Attempt)
            .filter(Attempt.user_id == int(session.user_id), Attempt.quiz_set_id == int(quiz_id))
            .order_by(Attempt.created_at.desc())
        )
        if getattr(session, "started_at", None) is not None:
            q = q.filter(Attempt.created_at >= session.started_at)
        attempt_record = q.first()

    if not attempt_record:
        raise HTTPException(status_code=404, detail="Attempt result not found")

    questions = (
        db.query(Question)
        .filter(Question.quiz_set_id == int(quiz_id))
        .order_by(Question.order_no.asc())
        .all()
    )
    q_by_id = {int(q.id): q for q in questions}

    breakdown = list(attempt_record.breakdown_json or [])
    by_qid = {}
    for item in breakdown:
        try:
            by_qid[int(item.get("question_id") or 0)] = item
        except Exception:
            continue

    questions_detail = []
    for q in questions:
        item = by_qid.get(int(q.id), {})
        options = list(getattr(q, "options", None) or [])
        student_answer_idx = item.get("chosen") if str(item.get("type") or q.type or "").lower() == "mcq" else None
        correct_answer_idx = int(getattr(q, "correct_index", -1)) if str(q.type or "").lower() == "mcq" else None

        try:
            student_answer_idx = int(student_answer_idx) if student_answer_idx is not None else None
        except Exception:
            student_answer_idx = None

        student_answer_text = item.get("answer_text")
        if str(q.type or "").lower() == "mcq":
            if student_answer_idx is not None and 0 <= student_answer_idx < len(options):
                student_answer_text = options[student_answer_idx]
            else:
                student_answer_text = None

        correct_answer_text = None
        if correct_answer_idx is not None and 0 <= correct_answer_idx < len(options):
            correct_answer_text = options[correct_answer_idx]

        enriched_item = dict(item or {})
        if not enriched_item.get("bloom_level"):
            enriched_item["bloom_level"] = getattr(q, "bloom_level", None)
        difficulty = _difficulty_from_breakdown_item(enriched_item)

        questions_detail.append({
            "question_id": int(q.id),
            "order_no": int(item.get("order_no") or getattr(q, "order_no", 0) or 0),
            "question_text": str(getattr(q, "stem", "") or ""),
            "type": str(getattr(q, "type", "mcq") or "mcq"),
            "bloom_level": item.get("bloom_level") or getattr(q, "bloom_level", None),
            "difficulty": difficulty,
            "topic": item.get("topic") or str(getattr(quiz, "topic", "") or ""),
            "options": options,
            "student_answer_idx": student_answer_idx,
            "correct_answer_idx": correct_answer_idx,
            "student_answer_text": student_answer_text,
            "correct_answer_text": correct_answer_text,
            "is_correct": bool(item.get("is_correct")) if str(q.type or "").lower() == "mcq" else None,
            "score_earned": int(item.get("score_points") or 0),
            "score_max": int(item.get("max_points") or (1 if str(q.type or "").lower() == "mcq" else 0)),
            "explanation": item.get("explanation") or getattr(q, "explanation", None),
            "sources": item.get("sources") or list(getattr(q, "sources", None) or []),
        })

    summary = score_breakdown(breakdown)
    for key in ("easy", "medium", "hard"):
        summary.setdefault("by_difficulty", {}).setdefault(key, {"earned": 0, "total": 0, "percent": 0.0})

    level_obj = classify_student_level(int(round(float(summary.get("overall", {}).get("percent") or attempt_record.score_percent or 0))))

    duration_seconds = _quiz_duration_map(quiz)
    spent = int(getattr(attempt_record, "duration_sec", 0) or 0)
    timed_out = bool(getattr(attempt_record, "is_late", False) or (duration_seconds and spent > int(duration_seconds)))

    title = str(getattr(quiz, "topic", "") or "").strip() or f"Quiz #{quiz_id}"

    result_detail = {
        "attempt_record_id": int(attempt_record.id),
        "quiz_id": int(quiz_id),
        "quiz_kind": str(getattr(quiz, "kind", "") or ""),
        "quiz_title": title,
        "score_percent": int(getattr(attempt_record, "score_percent", 0) or 0),
        "total_score_percent": float(summary.get("overall", {}).get("percent") or 0.0),
        "score_points": int(summary.get("overall", {}).get("earned") or 0),
        "max_points": int(summary.get("overall", {}).get("total") or 0),
        "classification": str(level_obj.get("level_key") or ""),
        "level_label": str(level_obj.get("label") or ""),
        "time_spent_seconds": spent,
        "timed_out": timed_out,
        "questions_detail": questions_detail,
        "summary": summary,
    }

    return {
        "request_id": request.state.request_id,
        "data": {"result_detail": result_detail},
        "error": None,
    }


@router.post("/attempts/{attempt_id}/submit")
def submit_attempt_by_id(request: Request, attempt_id: int, payload: SubmitAttemptByIdIn, db: Session = Depends(get_db)):
    started = db.query(UserSession).filter(UserSession.id == int(attempt_id)).first()
    if not started:
        raise HTTPException(status_code=404, detail="Attempt not found")

    quiz_id = _attempt_quiz_id(started)
    quiz = db.query(QuizSet).filter(QuizSet.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    allowed = (
        db.query(ClassroomAssessment.id)
        .join(ClassroomMember, ClassroomMember.classroom_id == ClassroomAssessment.classroom_id)
        .filter(
            ClassroomMember.user_id == int(started.user_id),
            ClassroomAssessment.assessment_id == int(quiz_id),
        )
        .first()
    )
    if not allowed:
        raise HTTPException(status_code=404, detail="Attempt not found")

    duration_seconds = _quiz_duration_map(quiz)
    spent, time_left_seconds = _attempt_timing(started, duration_seconds)
    _lock_attempt_if_expired(started, time_left_seconds=time_left_seconds)

    grace_seconds = int(duration_seconds or 0) + 30
    is_late = bool(started.locked_at is not None or spent > grace_seconds)
    snapshot_answers = list(started.answers_snapshot_json or [])
    used_snapshot = bool(is_late and snapshot_answers)
    submit_answers = snapshot_answers if used_snapshot else payload.answers
    duration_seconds = int(_quiz_duration_map(quiz) or 0)
    now = datetime.now(timezone.utc)
    started_at = _normalize_started_at_utc(started, now)
    spent = max(0, int((now - started_at).total_seconds()))
    grace_seconds = 30
    timed_out = bool(duration_seconds and spent > duration_seconds)

    lock_due_to_timeout = bool(duration_seconds and spent >= duration_seconds)
    if lock_due_to_timeout and started.locked_at is None:
        started.locked_at = now
    if lock_due_to_timeout and started.ended_at is None:
        started.ended_at = now

    late_by_seconds = max(0, spent - duration_seconds)
    is_late = bool(started.locked_at is not None or (duration_seconds and spent > (duration_seconds + grace_seconds)))

    snapshot_answers = started.answers_snapshot_json or []
    snapshot_non_empty = isinstance(snapshot_answers, list) and len(snapshot_answers) > 0
    used_snapshot = bool(is_late and snapshot_non_empty)

    answers_for_scoring = payload.answers
    late_note = None
    if used_snapshot:
        answers_for_scoring = snapshot_answers
    elif is_late and not snapshot_non_empty:
        late_note = "late_no_snapshot"

    questions = (
        db.query(Question)
        .filter(Question.quiz_set_id == int(quiz_id))
        .order_by(Question.order_no.asc())
        .all()
    )
    normalized_answers_for_event = _build_answer_list_from_questions(questions=questions, answers=answers_for_scoring)

    base = submit_assessment(
        db,
        assessment_id=quiz_id,
        user_id=int(started.user_id),
        duration_sec=spent,
        answers=submit_answers,
        duration_sec=min(spent, duration_seconds) if duration_seconds > 0 else spent,
        answers=answers_for_scoring,
    )
    if str(getattr(quiz, "kind", "") or "") == "diagnostic_post":
        ca_row = db.query(ClassroomAssessment).filter(ClassroomAssessment.assessment_id == int(quiz_id)).first()
        if ca_row:
            _ensure_class_final_notification(db, classroom_id=int(ca_row.classroom_id), final_quiz_id=int(quiz_id))

    attempt_id_created = int(base.get("attempt_id") or 0)
    if attempt_id_created > 0:
        attempt_row = db.query(Attempt).filter(Attempt.id == attempt_id_created).first()
        if attempt_row:
            attempt_row.is_late = bool(is_late)
            attempt_row.deadline_seconds = int(duration_seconds or 0)
            db.add(attempt_row)
            db.commit()

    linked_attempt_record_id = int(base.get("attempt_id") or 0)
    if linked_attempt_record_id > 0:
        started.linked_attempt_record_id = linked_attempt_record_id
    if started.ended_at is None:
        started.ended_at = datetime.now(timezone.utc)
    db.add(started)
    db.commit()
    db.refresh(started)

    timed_out = bool(duration_seconds and spent > int(duration_seconds))

    # Auto-trigger learning plan generation for diagnostic entry test submissions.
    try:
        if quiz.kind == "diagnostic_pre":
            from app.mas.base import AgentContext
            from app.mas.contracts import Event
            from app.mas.orchestrator import Orchestrator

            orch = Orchestrator(db=db)
            event = Event(
                type="ENTRY_TEST_SUBMITTED",
                user_id=int(started.user_id),
                payload={
                    "attempt_id": int(base.get("attempt_id") or 0),
                    "quiz_set_id": int(quiz_id),
                    "score": int(base.get("total_score_percent") or base.get("score_percent") or 0),
                    "breakdown": base.get("breakdown") or [],
                    "student_level": classify_student_level(int(base.get("total_score_percent") or base.get("score_percent") or 0))["level_key"],
                    "document_ids": [int(quiz.source_query_id)] if getattr(quiz, "source_query_id", None) else [],
                },
                trace_id=getattr(request.state, "request_id", None),
            )
            ctx = AgentContext(
                user_id=int(started.user_id),
                document_ids=[int(quiz.source_query_id)] if getattr(quiz, "source_query_id", None) else [],
            )

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(asyncio.to_thread(orch.run, event, ctx))
                else:
                    orch.run(event, ctx)
            except Exception:
                orch.run(event, ctx)  # synchronous fallback
    except Exception as exc:
        # Log warning but do not fail main submit flow.
        logging.getLogger(__name__).warning("Auto learning plan failed: %s", exc)

    breakdown = score_breakdown(base.get("breakdown") or [])
    level = classify_student_level(
        int(round(float(breakdown["overall"]["percent"]))))
    topics = [str(x) for x in (quiz.topic.split(
        ",") if quiz.topic else []) if x.strip()]
    multidim_profile = classify_student_multidim(
        breakdown=breakdown,
        time_spent_sec=spent,
        estimated_time_sec=duration_seconds,
        prev_attempts=[],
    )
    recommendations = build_recommendations(
        breakdown=breakdown, document_topics=topics, multidim_profile=multidim_profile)

    if is_late:
    if timed_out or is_late:
        base["is_late_submission"] = True
        base["late_by_seconds"] = int(late_by_seconds)
        if late_note:
            base["notes"] = "late_no_snapshot"
        elif used_snapshot:
            base["notes"] = (
                f"⚠️ Bài nộp trễ {int(late_by_seconds)} giây. "
                "Điểm được chấm theo snapshot tự động lưu trước deadline."
            )
        else:
            base["notes"] = (
                f"⚠️ Bài nộp trễ {int(late_by_seconds)} giây. "
                "Không có snapshot trước deadline, hệ thống chấm theo bài nộp hiện tại."
            )
    else:
        base["is_late_submission"] = False
        base["notes"] = "Bài nộp đúng hạn."

    base = _normalize_submit_synced_diagnostic(base, quiz_kind=getattr(quiz, "kind", None))

    # === AUTO-ASSIGN LEARNING PATH SAU KHI PHÂN LOẠI ===
    classroom_id_for_path = int(getattr(quiz, "classroom_id", 0) or 0)
    quiz_kind = str(getattr(quiz, "kind", "") or "").lower()
    should_auto_assign = quiz_kind in {"diagnostic_pre", "diagnostic_post"}
    weak_topics = [
        topic
        for topic, stat in ((breakdown.get("by_topic") or {}).items())
        if float((stat or {}).get("percent") or 0) < 65
    ]

    if should_auto_assign:
        try:
            doc_ids = _extract_quiz_document_ids(quiz)

            ca = db.query(ClassroomAssessment).filter(
                ClassroomAssessment.assessment_id == quiz_id
            ).first()
            if ca:
                classroom_id_for_path = int(getattr(ca, "classroom_id", 0) or classroom_id_for_path or 0)

            if not doc_ids:
                doc_ids = _infer_document_ids_from_topics(db, weak_topics)

            auto_plan = assign_learning_path(
                db,
                user_id=int(started.user_id),
                student_level=str(level.get("level_key") or "trung_binh"),
                document_ids=doc_ids,
                classroom_id=int(classroom_id_for_path) if classroom_id_for_path else 0,
            )
            _upsert_plan_weak_topics(
                db,
                plan_id=auto_plan.get("plan_id"),
                weak_topics=weak_topics,
            )

            base["learning_path_assigned"] = True
            base["learning_plan_id"] = auto_plan.get("plan_id")
            base["weak_topics"] = weak_topics
            base = _normalize_submit_synced_diagnostic(base, quiz_kind=getattr(quiz, "kind", None))
        except Exception as _e:
            logging.getLogger(__name__).warning(f"Auto-assign learning path failed: {_e}")
            base["learning_path_assigned"] = False
    else:
        base["learning_path_assigned"] = False

    try:
        ca_for_notify = db.query(ClassroomAssessment).filter(
            ClassroomAssessment.assessment_id == quiz_id
        ).first()
        if ca_for_notify:
            quiz_for_notify = db.query(QuizSet).filter(QuizSet.id == quiz_id).first()
            exam_kind_for_notify = getattr(quiz_for_notify, "kind", "unknown")
            notify_teacher_student_finished(
                db,
                student_id=int(started.user_id),
                classroom_id=int(ca_for_notify.classroom_id),
                exam_kind=exam_kind_for_notify,
                score_percent=float(breakdown["overall"]["percent"]),
                classification=str(level.get("level_key") or "trung_binh"),
            )
    except Exception:
        pass

    try:
        if str(getattr(quiz, "kind", "") or "").lower() == "diagnostic_post":
            ca = db.query(ClassroomAssessment).filter(ClassroomAssessment.assessment_id == int(quiz_id)).first()
            if ca:
                classroom_id = int(ca.classroom_id)
                student_rows = db.query(ClassroomMember.user_id).filter(ClassroomMember.classroom_id == classroom_id).all()
                student_ids = {int(uid) for uid, in student_rows}
                q_submitted = (
                    db.query(Attempt.user_id)
                    .join(QuizSet, QuizSet.id == Attempt.quiz_set_id)
                    .join(ClassroomAssessment, ClassroomAssessment.assessment_id == QuizSet.id)
                    .filter(
                        ClassroomAssessment.classroom_id == classroom_id,
                        QuizSet.kind == "diagnostic_post",
                    )
                )
                if student_ids:
                    q_submitted = q_submitted.filter(Attempt.user_id.in_(student_ids))
                submitted_rows = q_submitted.distinct().all()
                submitted_ids = {int(uid) for uid, in submitted_rows}
                if student_ids and submitted_ids == student_ids:
                    classroom_obj = db.query(Classroom).filter(Classroom.id == classroom_id).first()
                    teacher_id = int(getattr(classroom_obj, "teacher_id", 0) or 0)
                    if teacher_id:
                        existing = (
                            db.query(Notification)
                            .filter(Notification.user_id == teacher_id, Notification.type == "report_ready")
                            .order_by(Notification.created_at.desc())
                            .limit(20)
                            .all()
                        )
                        exists = any(int((n.payload_json or {}).get("classroom_id") or 0) == classroom_id for n in existing)
                        if not exists:
                            db.add(
                                Notification(
                                    user_id=teacher_id,
                                    type="report_ready",
                                    title="Báo cáo lớp đã sẵn sàng",
                                    message=f"Tất cả học sinh lớp {classroom_id} đã nộp bài final.",
                                    payload_json={"classroom_id": classroom_id},
                                    is_read=False,
                                )
                            )
                            db.commit()
    except Exception:
        pass

    base = _normalize_synced_diagnostic(base)

    if str(getattr(quiz, "kind", "") or "") == "diagnostic_pre":
        evt = Event(
            type="ENTRY_TEST_SUBMITTED",
            user_id=int(started.user_id),
            payload={
                "quiz_id": int(quiz_id),
                "user_id": int(started.user_id),
                "answers": normalized_answers_for_event,
                "duration_sec": int(spent),
                "classroom_id": int(getattr(quiz, "classroom_id", 0) or 0),
            },
            trace_id=str(getattr(request.state, "request_id", "") or None),
        )
        _publish_mas_event_non_blocking(db, event=evt)
    base = _normalize_submit_synced_diagnostic(base, quiz_kind=getattr(quiz, "kind", None))

    return {
        "request_id": request.state.request_id,
        "data": {
            **base,
            "time_spent_seconds": spent,
            "duration_seconds": duration_seconds,
            "timed_out": timed_out,
            "is_late": is_late,
            "used_snapshot": used_snapshot,
            "locked": bool(started.locked_at),
            "time_left_seconds": max(0, time_left_seconds),
            "is_late": bool(is_late),
            "used_snapshot": bool(used_snapshot),
            "score_breakdown": breakdown,
            "classification": level,
            "recommendations": recommendations,
        },
        "error": None,
    }


@router.post("/lms/student/{user_id}/assign-learning-path")
def assign_student_path(
    request: Request,
    user_id: int,
    payload: AssignPathIn,
    db: Session = Depends(get_db),
):
    result = assign_learning_path(
        db,
        user_id=int(user_id),
        student_level=str(payload.student_level),
        document_ids=[int(x) for x in (payload.document_ids or [])],
        classroom_id=int(payload.classroom_id),
    )
    return {"request_id": request.state.request_id, "data": result, "error": None}


@router.get("/teacher/notifications")
def get_teacher_notifications(request: Request, teacher_id: int, db: Session = Depends(get_db)):
    from app.services.notification_service import get_notifications_for_teacher

    notifs = get_notifications_for_teacher(int(teacher_id))
    return {"request_id": request.state.request_id, "data": notifs, "error": None}


@router.post("/teacher/notifications/{notif_id}/read")
def mark_notification_read(request: Request, notif_id: int, db: Session = Depends(get_db)):
    from app.services.notification_service import mark_read

    mark_read(int(notif_id))
    return {"request_id": request.state.request_id, "data": {"ok": True}, "error": None}


@router.post("/lms/assign-path")
def assign_path_by_quiz(
    request: Request,
    payload: AssignPathByQuizIn,
    db: Session = Depends(get_db),
):
    latest = (
        db.query(Attempt)
        .filter(Attempt.quiz_set_id == int(payload.quiz_id), Attempt.user_id == int(payload.user_id))
        .order_by(Attempt.created_at.desc())
        .first()
    )
    if not latest:
        raise HTTPException(status_code=404, detail="Attempt not found")

    quiz = db.query(QuizSet).filter(QuizSet.id == int(payload.quiz_id)).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    breakdown = score_breakdown(latest.breakdown_json or [])
    level = classify_student_level(int(round(float((breakdown.get("overall") or {}).get("percent") or 0))))
    doc_ids = [int(x) for x in (getattr(quiz, "document_ids_json", None) or []) if str(x).isdigit()]

    result = assign_learning_path(
        db,
        user_id=int(payload.user_id),
        student_level=str(level["level_key"]),
        document_ids=doc_ids,
        classroom_id=int(payload.classroom_id or 0),
    )

    return {
        "request_id": request.state.request_id,
        "data": {
            "user_id": int(payload.user_id),
            "quiz_id": int(payload.quiz_id),
            "classroom_id": int(payload.classroom_id or 0),
            "student_level": level,
            "assigned_path": result,
        },
        "error": None,
    }


@router.get("/lms/student/{user_id}/my-path")
def get_my_path(request: Request, user_id: int, db: Session = Depends(get_db)):
    profile = db.query(LearnerProfile).filter(
        LearnerProfile.user_id == int(user_id)
    ).first()
    plan = (
        db.query(LearningPlan)
        .filter(LearningPlan.user_id == int(user_id))
        .order_by(LearningPlan.id.desc())
        .first()
    )

    plan_json = dict(plan.plan_json or {}) if plan and isinstance(plan.plan_json, dict) else {}
    assigned_tasks = plan_json.get("assigned_tasks") if isinstance(plan_json.get("assigned_tasks"), list) else []
    weak_topics = [str(t) for t in (plan_json.get("weak_topics") or []) if str(t).strip()]

    level_key = str((profile.level if profile else None) or (plan.level if plan else None) or "trung_binh")
    level_map = {
        "gioi": {"label": "Giỏi", "color": "green"},
        "kha": {"label": "Khá", "color": "blue"},
        "trung_binh": {"label": "Trung Bình", "color": "orange"},
        "yeu": {"label": "Yếu", "color": "red"},
    }
    level_info = level_map.get(level_key, level_map["trung_binh"])

    total_tasks = len(assigned_tasks)
    completed_tasks = 0
    progress_percent = 0.0
    if plan:
        completed_rows = (
            db.query(LearningPlanTaskCompletion)
            .filter(
                LearningPlanTaskCompletion.plan_id == int(plan.id),
                LearningPlanTaskCompletion.completed.is_(True),
            )
            .all()
        )
        completed_tasks = len(completed_rows)
        if total_tasks > 0:
            progress_percent = round((completed_tasks / total_tasks) * 100, 2)

    return {
        "request_id": request.state.request_id,
        "data": {
            "student_level": level_key,
            "level": {
                "key": level_key,
                "label": level_info["label"],
                "color": level_info["color"],
            },
            "progress": {
                "completed_tasks": completed_tasks,
                "total_tasks": total_tasks,
                "percent": progress_percent,
            },
            "plan": {
                "plan_id": int(plan.id) if plan else None,
                "assigned_tasks": assigned_tasks,
                "tasks": assigned_tasks,
                "weak_topics": weak_topics,
            },
            "plan_id": int(plan.id) if plan else None,
            "assigned_tasks": assigned_tasks,
            "weak_topics": weak_topics,
        },
        "error": None,
    }




@router.get("/lms/student/{user_id}/topic-progress")
def get_topic_progress(
    request: Request,
    user_id: int,
    classroom_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
):
    plan_q = db.query(LearningPlan).filter(LearningPlan.user_id == int(user_id))
    if classroom_id is not None:
        plan_q = plan_q.filter(LearningPlan.classroom_id == int(classroom_id))

    plan = plan_q.order_by(LearningPlan.id.desc()).first()
    if not plan:
        return {"request_id": request.state.request_id, "data": {"topics": []}, "error": None}

    plan_json = plan.plan_json if isinstance(plan.plan_json, dict) else {}
    assigned_tasks = plan_json.get("assigned_tasks") if isinstance(plan_json.get("assigned_tasks"), list) else []
    days = plan_json.get("days") if isinstance(plan_json.get("days"), list) else []

    completed_rows = (
        db.query(LearningPlanTaskCompletion)
        .filter(
            LearningPlanTaskCompletion.plan_id == int(plan.id),
            LearningPlanTaskCompletion.completed.is_(True),
        )
        .all()
    )
    completed_set = {(int(r.day_index), int(r.task_index)) for r in completed_rows}

    attempted_quiz_ids = {
        int(x[0])
        for x in db.query(Attempt.quiz_set_id).filter(Attempt.user_id == int(user_id)).distinct().all()
        if x and x[0] is not None
    }

    by_topic: dict[str, dict[str, int | float | str]] = {}

    for t in assigned_tasks:
        if not isinstance(t, dict):
            continue
        topic = str(t.get("topic_title") or t.get("topic") or "Chưa phân loại").strip() or "Chưa phân loại"
        if topic not in by_topic:
            by_topic[topic] = {"topic": topic, "completed_tasks": 0, "total_tasks": 0}
        by_topic[topic]["total_tasks"] = int(by_topic[topic]["total_tasks"]) + 1

        quiz_id = t.get("quiz_id")
        if str(quiz_id).isdigit() and int(quiz_id) in attempted_quiz_ids:
            by_topic[topic]["completed_tasks"] = int(by_topic[topic]["completed_tasks"]) + 1

    for day in days:
        if not isinstance(day, dict):
            continue
        day_index = int(day.get("day_index") or 0)
        tasks = day.get("tasks") if isinstance(day.get("tasks"), list) else []
        for task_index, task in enumerate(tasks):
            if not isinstance(task, dict):
                continue
            topic = str(task.get("topic_title") or task.get("topic") or "").strip()
            if not topic:
                continue
            if topic not in by_topic:
                by_topic[topic] = {"topic": topic, "completed_tasks": 0, "total_tasks": 0}
            by_topic[topic]["total_tasks"] = int(by_topic[topic]["total_tasks"]) + 1
            if (int(day_index), int(task_index)) in completed_set:
                by_topic[topic]["completed_tasks"] = int(by_topic[topic]["completed_tasks"]) + 1

    out = []
    for row in by_topic.values():
        total = max(0, int(row.get("total_tasks") or 0))
        done = max(0, min(total, int(row.get("completed_tasks") or 0)))
        pct = round((done / total) * 100, 2) if total > 0 else 0.0
        out.append({"topic": row.get("topic"), "completed_tasks": done, "total_tasks": total, "percent": pct})

    out.sort(key=lambda x: str(x.get("topic") or "").lower())
    return {"request_id": request.state.request_id, "data": {"topics": out}, "error": None}

@router.get("/students/{student_id}/recommendations")
def student_recommendations(request: Request, student_id: int, db: Session = Depends(get_db)):
    latest = (
        db.query(Attempt)
        .filter(Attempt.user_id == int(student_id))
        .order_by(Attempt.created_at.desc())
        .first()
    )
    if not latest:
        return {"request_id": request.state.request_id, "data": {"student_id": student_id, "recommendations": []}, "error": None}
    breakdown = score_breakdown(latest.breakdown_json or [])
    quiz = db.query(QuizSet).filter(
        QuizSet.id == int(latest.quiz_set_id)).first()
    topics = [str(x) for x in (quiz.topic.split(
        ",") if quiz and quiz.topic else []) if x.strip()]
    multidim_profile = classify_student_multidim(
        breakdown=breakdown,
        time_spent_sec=int(getattr(latest, "duration_sec", 0) or 0),
        estimated_time_sec=_quiz_duration_map(quiz) if quiz else 1800,
        prev_attempts=[],
    )
    recs = build_recommendations(breakdown=breakdown, document_topics=topics, multidim_profile=multidim_profile)
    assignments = [
        {"topic": r["topic"], "material": r["material"],
            "exercise_set": r["exercise"], "status": "assigned"}
        for r in recs
    ]
    return {"request_id": request.state.request_id, "data": {"student_id": student_id, "recommendations": recs, "assignments": assignments}, "error": None}




@router.get("/lms/student/{user_id}/progress")
def lms_student_progress(request: Request, user_id: int, classroom_id: int = Query(..., ge=1), db: Session = Depends(get_db)):
    def _latest_attempt_for_kind(kind: str):
        return (
            db.query(Attempt)
            .join(ClassroomAssessment, ClassroomAssessment.assessment_id == Attempt.quiz_set_id)
            .join(QuizSet, QuizSet.id == Attempt.quiz_set_id)
            .filter(
                Attempt.user_id == int(user_id),
                ClassroomAssessment.classroom_id == int(classroom_id),
                QuizSet.kind == kind,
            )
            .order_by(Attempt.created_at.desc(), Attempt.id.desc())
            .first()
        )

    pre_attempt = _latest_attempt_for_kind("diagnostic_pre")
    post_attempt = _latest_attempt_for_kind("diagnostic_post")

    pre_score = float(pre_attempt.score_percent) if pre_attempt else None
    post_score = float(post_attempt.score_percent) if post_attempt else None
    delta = (post_score - pre_score) if pre_score is not None and post_score is not None else None

    timestamps = [x.created_at for x in (pre_attempt, post_attempt) if getattr(x, "created_at", None) is not None]
    updated_at = max(timestamps).isoformat() if timestamps else None

    data = {
        "pre_score": pre_score,
        "post_score": post_score,
        "delta": delta,
        "pre_attempt_id": int(pre_attempt.id) if pre_attempt else None,
        "post_attempt_id": int(post_attempt.id) if post_attempt else None,
        "updated_at": updated_at,
    }
    return {"request_id": request.state.request_id, "data": data, "error": None}

@router.get("/students/{user_id}/progress")
def student_progress_comparison(request: Request, user_id: int, classroomId: int = Query(..., ge=1), db: Session = Depends(get_db)):
    data = get_student_progress_comparison(user_id=int(user_id), classroom_id=int(classroomId), db=db)
    return {"request_id": request.state.request_id, "data": data, "error": None}




@router.get("/teacher/reports/{student_id}")
def teacher_student_reports(request: Request, student_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == int(student_id))
        .order_by(Notification.created_at.desc())
        .all()
    )
    data = []
    for r in rows:
        payload = r.payload_json if isinstance(r.payload_json, dict) else {}
        data.append(
            {
                "id": int(r.id),
                "type": str(getattr(r.type, "value", r.type)),
                "title": r.title,
                "message": r.message,
                "is_read": bool(r.is_read),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "payload": payload,
            }
        )
    return {"request_id": request.state.request_id, "data": {"student_id": int(student_id), "reports": data}, "error": None}


@router.post("/teacher/reports/{report_id}/mark-read")
def teacher_report_mark_read(request: Request, report_id: int, db: Session = Depends(get_db)):
    row = db.query(Notification).filter(Notification.id == int(report_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    if not row.is_read:
        row.is_read = True
        db.commit()
        db.refresh(row)
    return {"request_id": request.state.request_id, "data": {"id": int(row.id), "is_read": bool(row.is_read)}, "error": None}

@router.get("/teacher/reports")
def teacher_reports(request: Request, classroom_id: int = 1, db: Session = Depends(get_db)):
    return teacher_report(request=request, classroom_id=classroom_id, db=db)


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
    level = classify_student_level(
        int(round(float(breakdown["overall"]["percent"]))))

    q = db.query(QuizSet).filter(QuizSet.id == int(assessment_id)).first()
    topics = [str(x) for x in (q.topic.split(
        ",") if q and q.topic else []) if x.strip()]

    prev_rows = (
        db.query(Attempt)
        .filter(Attempt.user_id == int(payload.user_id))
        .order_by(Attempt.created_at.desc())
        .limit(5)
        .all()
    )
    prev_attempts = []
    for row in reversed(prev_rows):
        prev_br = score_breakdown(row.breakdown_json or [])
        prev_attempts.append(float((prev_br.get("overall") or {}).get("percent") or 0.0))

    estimated_time_sec = _quiz_duration_map(q) if q else 1800
    multidim_profile = classify_student_multidim(
        breakdown=breakdown,
        time_spent_sec=int(payload.duration_sec),
        estimated_time_sec=estimated_time_sec,
        prev_attempts=prev_attempts,
    )
    recommendations = build_recommendations(
        breakdown=breakdown, document_topics=topics, multidim_profile=multidim_profile)

    try:
        q_obj = db.query(QuizSet).filter(QuizSet.id == int(assessment_id)).first()
        doc_ids = getattr(q_obj, "document_ids_json", None) or []
        if doc_ids:
            path_result = assign_learning_path(
                db,
                user_id=int(payload.user_id),
                student_level=str(level["level_key"]),
                document_ids=[int(x) for x in doc_ids],
            )
            base["assigned_learning_path"] = path_result
    except Exception:
        base["assigned_learning_path"] = None  # Không bao giờ làm hỏng flow chính

    base = _normalize_submit_synced_diagnostic(base, quiz_kind=getattr(q, "kind", None))

    persisted = persist_multidim_profile(db, user_id=int(payload.user_id), profile=multidim_profile)

    assignment_ids: list[int] = []
    if q and getattr(q, "document_ids_json", None):
        doc_ids = [int(x) for x in (q.document_ids_json or [])]
        if doc_ids:
            assignment_ids = assign_topic_materials(
                db,
                student_id=int(payload.user_id),
                classroom_id=int(getattr(q, "classroom_id", 0) or 0),
                student_level=str(level["level_key"]),
                weak_topics=breakdown.get("weak_topics") or [],
                document_id=int(doc_ids[0]),
            )

    base["score_breakdown"] = breakdown
    base["student_level"] = level
    base = _normalize_synced_diagnostic(base)
    base["multidim_profile"] = persisted["profile"]
    base["multidim_profile_key"] = persisted["key"]
    base["recommendations"] = recommendations
    base["assignments_created"] = len(assignment_ids)
    base["assignment_ids"] = assignment_ids
    return {"request_id": request.state.request_id, "data": base, "error": None}




@router.get("/profile/{user_id}/multidim")
def get_multidim_profile(request: Request, user_id: int, db: Session = Depends(get_db)):
    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == int(user_id)).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    mastery = dict(profile.mastery_json or {})
    latest = mastery.get("multidim_profile_latest") or {}
    hist_items = []
    for key, value in mastery.items():
        if str(key).startswith("multidim_profile_") and key != "multidim_profile_latest" and isinstance(value, dict):
            hist_items.append((str(key), value))
    hist_items.sort(key=lambda x: x[0])

    trend = []
    for key, item in hist_items:
        trend.append(
            {
                "timestamp": key.replace("multidim_profile_", ""),
                "primary_level": item.get("primary_level"),
                "knowledge_depth": item.get("knowledge_depth"),
                "time_efficiency": item.get("time_efficiency"),
                "consistency": item.get("consistency"),
                "recommended_pace": item.get("recommended_pace"),
            }
        )

    return {
        "request_id": request.state.request_id,
        "data": {
            "user_id": int(user_id),
            "latest": latest,
            "trend": trend[-20:],
        },
        "error": None,
    }



def _quiz_kind_map_for_classroom(db: Session, classroom_id: int) -> dict[str, int]:
    rows = (
        db.query(QuizSet.id, QuizSet.kind)
        .join(ClassroomAssessment, ClassroomAssessment.assessment_id == QuizSet.id)
        .filter(ClassroomAssessment.classroom_id == int(classroom_id))
        .all()
    )
    out: dict[str, int] = {}
    for quiz_id, kind in rows:
        if kind and str(kind) not in out:
            out[str(kind)] = int(quiz_id)
    return out


def _ensure_class_final_notification(db: Session, *, classroom_id: int, final_quiz_id: int) -> None:
    classroom = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    if not classroom:
        return

    student_ids = [
        int(uid)
        for uid, in db.query(ClassroomMember.user_id).filter(
            ClassroomMember.classroom_id == int(classroom_id),
            ClassroomMember.user_id != int(classroom.teacher_id),
        ).all()
    ]
    if not student_ids:
        return

    submitted_ids = {
        int(uid)
        for uid, in db.query(Attempt.user_id)
        .filter(Attempt.quiz_set_id == int(final_quiz_id), Attempt.user_id.in_(student_ids))
        .distinct()
        .all()
    }
    if not set(student_ids).issubset(submitted_ids):
        return

    exists = db.query(Notification.id).filter(
        Notification.user_id == int(classroom.teacher_id),
        Notification.type == "class_final_ready",
        Notification.quiz_id == int(final_quiz_id),
    ).first()
    if exists:
        return

    db.add(
        Notification(
            user_id=int(classroom.teacher_id),
            teacher_id=int(classroom.teacher_id),
            quiz_id=int(final_quiz_id),
            type="class_final_ready",
            title="Báo cáo lớp sẵn sàng",
            message="Tất cả học sinh đã nộp final. Báo cáo sẵn sàng.",
            payload_json={"classroom_id": int(classroom_id), "quiz_id": int(final_quiz_id)},
            is_read=False,
        )
    )
    db.commit()


def _build_enhanced_teacher_report(*, classroom_id: int, db: Session) -> dict:
    quiz_kind_map = _quiz_kind_map_for_classroom(db, classroom_id)
    pre_quiz_id = quiz_kind_map.get("diagnostic_pre")
    final_quiz_id = quiz_kind_map.get("diagnostic_post")

    classroom = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    teacher_id = int(classroom.teacher_id) if classroom else None
    members = db.query(ClassroomMember).filter(ClassroomMember.classroom_id == int(classroom_id)).all()

    per_student: list[dict] = []
    topic_heatmap_acc: dict[str, dict[str, float]] = {}

    for member in members:
        uid = int(member.user_id)
        if teacher_id and uid == teacher_id:
            continue

        pre_attempt = None
        if pre_quiz_id:
            pre_attempt = (
                db.query(Attempt)
                .filter(Attempt.user_id == uid, Attempt.quiz_set_id == int(pre_quiz_id))
                .order_by(Attempt.created_at.desc())
                .first()
            )
        final_attempt = None
        if final_quiz_id:
            final_attempt = (
                db.query(Attempt)
                .filter(Attempt.user_id == uid, Attempt.quiz_set_id == int(final_quiz_id))
                .order_by(Attempt.created_at.desc())
                .first()
            )

        placement_score = float(pre_attempt.score_percent) if pre_attempt else None
        final_score = float(final_attempt.score_percent) if final_attempt else None
        improvement = round(final_score - placement_score, 2) if placement_score is not None and final_score is not None else None

        breakdown_candidates = [x.breakdown_json or [] for x in [pre_attempt, final_attempt] if x]
        weak_topics = analyze_topic_weak_points(breakdown_candidates) if breakdown_candidates else []
        final_breakdown = score_breakdown((final_attempt.breakdown_json if final_attempt else []) or [])
        by_topic = final_breakdown.get("by_topic") or {}
        strong_topics = [topic for topic, stat in by_topic.items() if float((stat or {}).get("percent") or 0.0) >= 75.0]

        latest_plan = (
            db.query(LearningPlan)
            .filter(LearningPlan.user_id == uid, LearningPlan.classroom_id == int(classroom_id))
            .order_by(LearningPlan.created_at.desc())
            .first()
        )
        homework_completion_rate = 0.0
        if latest_plan:
            total_days = max(1, int(latest_plan.days_total or 0))
            task_done = db.query(LearningPlanTaskCompletion).filter(
                LearningPlanTaskCompletion.plan_id == int(latest_plan.id),
                LearningPlanTaskCompletion.completed.is_(True),
            ).count()
            hw_done = db.query(LearningPlanHomeworkSubmission).filter(
                LearningPlanHomeworkSubmission.plan_id == int(latest_plan.id),
                LearningPlanHomeworkSubmission.user_id == uid,
            ).count()
            homework_completion_rate = round(min(1.0, (float(task_done + hw_done) / float(total_days * 2))) * 100, 2)

        tutor_sessions_count = db.query(UserSession).filter(UserSession.user_id == uid, UserSession.type == "tutor_chat").count()

        weak_topic_names = [str(x.get("topic") or "") for x in weak_topics if isinstance(x, dict) and x.get("topic")]
        if llm_available():
            ai_comment = chat_text(
                f"Nhận xét 1-2 câu cho học sinh với placement={placement_score}, final={final_score}, improvement={improvement}, weak_topics={weak_topic_names}",
                max_tokens=100,
            )
        else:
            if improvement is not None and improvement < 0:
                ai_comment = "Điểm cuối kỳ giảm, cần can thiệp theo các chủ đề yếu và tăng hỗ trợ cá nhân."
            elif weak_topic_names:
                ai_comment = f"Cần củng cố các chủ đề: {', '.join(weak_topic_names[:3])}."
            else:
                ai_comment = "Tiến độ ổn định, tiếp tục duy trì lộ trình học."

        per_student.append(
            {
                "student_id": uid,
                "student_name": resolve_student_name(db, uid),
                "placement_score": placement_score,
                "final_score": final_score,
                "improvement": improvement,
                "weak_topics": weak_topics,
                "strong_topics": strong_topics,
                "homework_completion_rate": homework_completion_rate,
                "tutor_sessions_count": int(tutor_sessions_count),
                "needs_support": bool((improvement is not None and improvement < 0) or (final_score is not None and final_score < 50)),
                "ai_comment": ai_comment,
            }
        )

        for topic, stat in by_topic.items():
            bucket = topic_heatmap_acc.setdefault(str(topic), {"sum": 0.0, "count": 0.0})
            bucket["sum"] += float((stat or {}).get("percent") or 0.0)
            bucket["count"] += 1

    final_scores = [float(s["final_score"]) for s in per_student if s.get("final_score") is not None]
    improvements = [float(s["improvement"]) for s in per_student if s.get("improvement") is not None]
    class_summary = {
        "total_students": len(per_student),
        "students_with_final": len(final_scores),
        "average_final_score": round(sum(final_scores) / max(1, len(final_scores)), 2) if final_scores else 0.0,
        "average_improvement": round(sum(improvements) / max(1, len(improvements)), 2) if improvements else 0.0,
    }
    topic_heatmap = {
        topic: {"avg_score": round(acc["sum"] / max(1.0, acc["count"]), 2), "students_count": int(acc["count"])}
        for topic, acc in topic_heatmap_acc.items()
    }

    if llm_available():
        ai_class_narrative = generate_class_narrative(per_student)
    else:
        ai_class_narrative = "Lớp có sự phân hóa kết quả, cần hỗ trợ nhóm học sinh điểm thấp và củng cố theo topic yếu."

    return {
        "classroom_id": int(classroom_id),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "class_summary": class_summary,
        "per_student": per_student,
        "topic_heatmap": topic_heatmap,
        "ai_class_narrative": ai_class_narrative,
        "recommendations_for_teacher": [
            "Theo dõi nhóm học sinh có improvement âm hoặc final dưới 50.",
            "Ưu tiên ôn tập theo các topic có điểm heatmap thấp.",
            "Khuyến khích dùng tutor AI đều đặn cho học sinh có ít tutor sessions.",
        ],
    }

@router.get("/lms/teacher/report/{classroom_id}")
def teacher_report(request: Request, classroom_id: int, db: Session = Depends(get_db)):
    classroom_id = int(classroom_id)
    if classroom_id in _report_cache and time.time() - _report_cache_time.get(classroom_id, 0) < 1800:
        report = _report_cache[classroom_id]
    else:
        report = _build_enhanced_teacher_report(classroom_id=classroom_id, db=db)
        _report_cache[classroom_id] = report
        _report_cache_time[classroom_id] = time.time()
    return {"request_id": request.state.request_id, "data": report, "error": None}


def _render_teacher_report_html(report: dict[str, object]) -> str:
    students = report.get("students") or []
    rows = []
    for s in students:
        ai = s.get("ai_evaluation") or {}
        topic_scores = s.get("topic_scores") or {}
        topic_text = ", ".join(f"{k}: {v}" for k, v in topic_scores.items()) or "N/A"
        rows.append(
            f"""
            <tr>
              <td>{s.get('name')}</td>
              <td>{s.get('diagnostic_score')}</td>
              <td>{s.get('final_score')}</td>
              <td>{s.get('improvement_pct')}</td>
              <td>{s.get('level')}</td>
              <td>{topic_text}</td>
              <td>{ai.get('summary', '')}</td>
            </tr>
            """
        )

    class_summary = report.get("class_summary") or {}
    return f"""
    <html>
      <head>
        <meta charset='utf-8' />
        <title>Teacher Report</title>
        <style>
          body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2937; }}
          h1 {{ margin-bottom: 4px; }}
          .meta {{ color: #4b5563; margin-bottom: 16px; }}
          .summary {{ background: #f3f4f6; padding: 12px; border-radius: 8px; margin-bottom: 16px; }}
          table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
          th, td {{ border: 1px solid #e5e7eb; padding: 8px; vertical-align: top; }}
          th {{ background: #f9fafb; text-align: left; }}
        </style>
      </head>
      <body>
        <h1>Báo cáo giáo viên - Lớp {report.get('classroom_id')}</h1>
        <div class='meta'>Generated at: {report.get('generated_at')}</div>
        <div class='summary'>
          <b>Đánh giá tổng quan:</b> {class_summary.get('overall_assessment', '')}<br/>
          <b>Avg improvement:</b> {class_summary.get('avg_improvement', 0)}<br/>
          <b>Top performers:</b> {', '.join(class_summary.get('top_performers') or []) or 'N/A'}<br/>
          <b>Needs attention:</b> {', '.join(class_summary.get('needs_attention') or []) or 'N/A'}
        </div>
        <table>
          <thead>
            <tr>
              <th>Học sinh</th><th>Đầu vào</th><th>Cuối kỳ</th><th>Cải thiện (%)</th><th>Mức</th><th>Topic scores</th><th>AI nhận xét</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows)}
          </tbody>
        </table>
      </body>
    </html>
    """


@router.get("/lms/teacher/report/{classroom_id}/export")
@router.get("/v1/lms/teacher/report/{classroom_id}/export")
def export_teacher_report(
    request: Request,
    classroom_id: int,
    format: str = Query("html"),
    teacher_id: int | None = Query(default=None),
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    classroom = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    authorized = False
    if current_user and str(getattr(current_user, "role", "")).lower() == "teacher":
        authorized = int(getattr(current_user, "id", 0) or 0) == int(classroom.teacher_id)

    if not authorized and teacher_id is not None:
        authorized = int(teacher_id) == int(classroom.teacher_id)

    if not authorized:
        raise HTTPException(status_code=403, detail="Teacher access required")

    export_format = str(format or "html").strip().lower()
    classroom_id = int(classroom_id)

    if export_format == "xlsx":
        xlsx_path = export_classroom_gradebook_xlsx(db=db, classroom_id=classroom_id)
        return FileResponse(
            str(xlsx_path),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=f"diem_lop_{classroom_id}.xlsx",
        )

    if classroom_id in _report_cache and time.time() - _report_cache_time.get(classroom_id, 0) < 1800:
        report = _report_cache[classroom_id]
    else:
        report = generate_full_teacher_report(classroom_id=classroom_id, db=db)
        _report_cache[classroom_id] = report
        _report_cache_time[classroom_id] = time.time()

    if export_format == "pdf":
        pdf_path = export_report_pdf(report, name=f"teacher_classroom_{classroom_id}")
        return FileResponse(pdf_path, media_type="application/pdf", filename=f"classroom_{classroom_id}_report.pdf")

    if export_format == "html":
        template = _templates.get_template("teacher_report.html")
        rendered = template.render(report=report, generated_date=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
        return HTMLResponse(content=rendered, media_type="text/html; charset=utf-8")

    if export_format == "json":
        return {
            "request_id": request.state.request_id,
            "data": report,
            "error": None,
        }

    raise HTTPException(status_code=400, detail="Supported formats: pdf, xlsx, html, json")


@router.get("/lms/student/{user_id}/report/export")
@router.get("/v1/lms/student/{user_id}/report/export")
def export_student_report(
    user_id: int,
    format: str = Query("pdf"),
    db: Session = Depends(get_db),
):
    student = db.query(User).filter(User.id == int(user_id)).first()
    attempts = db.query(Attempt).filter(Attempt.user_id == int(user_id)).order_by(Attempt.created_at.desc()).limit(50).all()
    pre = [float(a.score_percent or 0) for a in attempts if str(getattr(a.quiz_set, "kind", "")) in ("entry_test", "diagnostic_pre")]
    post = [float(a.score_percent or 0) for a in attempts if str(getattr(a.quiz_set, "kind", "")) in ("final_exam", "diagnostic_post")]
    report = {
        "students": [{
            "student_id": int(user_id),
            "name": str(getattr(student, "full_name", "") or f"User #{user_id}"),
            "entry_score": pre[0] if pre else 0,
            "mid_score": 0,
            "final_score": post[0] if post else 0,
            "level": str(getattr(student, "level", "") or ""),
            "topic_scores": {},
            "study_time_minutes": 0,
        }],
        "summary": {"attempt_count": len(attempts)},
    }
    export_format = str(format or "pdf").strip().lower()
    if export_format == "pdf":
        path = export_report_pdf(report, name=f"student_{user_id}")
        return FileResponse(path, media_type="application/pdf", filename=f"student_{user_id}_report.pdf")
    if export_format == "xlsx":
        path = export_report_xlsx(report, name=f"student_{user_id}")
        return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=f"student_{user_id}_report.xlsx")
    raise HTTPException(status_code=400, detail="Supported formats: pdf|xlsx")


@router.get("/lms/classroom/{classroom_id}/final-report")
def classroom_final_report(request: Request, classroom_id: int, db: Session = Depends(get_db)):
    report = build_classroom_final_report(db=db, classroom_id=int(classroom_id))
    return {"request_id": request.state.request_id, "data": report, "error": None}


@router.get("/lms/classroom/{classroom_id}/final-report/pdf")
def classroom_final_report_pdf(request: Request, classroom_id: int, db: Session = Depends(get_db)):
    _ = request
    report = build_classroom_final_report(db=db, classroom_id=int(classroom_id))
    pdf_path = export_classroom_final_report_pdf(report=report, classroom_id=int(classroom_id))
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"classroom_{classroom_id}_final_report.pdf")

@router.get("/lms/students/{student_id}/assignments")
def list_student_assignments(request: Request, student_id: int, classroom_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(StudentAssignment).filter(StudentAssignment.student_id == int(student_id))
    if classroom_id is not None:
        q = q.filter(StudentAssignment.classroom_id == int(classroom_id))
    rows = q.order_by(StudentAssignment.created_at.desc()).all()
    return {
        "request_id": request.state.request_id,
        "data": [
            {
                "id": int(r.id),
                "student_id": int(r.student_id),
                "classroom_id": int(r.classroom_id),
                "topic_id": int(r.topic_id) if r.topic_id else None,
                "document_id": int(r.document_id),
                "assignment_type": str(r.assignment_type),
                "student_level": str(r.student_level),
                "status": str(r.status),
                "due_date": r.due_date.isoformat() if r.due_date else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in rows
        ],
        "error": None,
    }


@router.get("/lms/students/{student_id}/assignments/{assignment_id}")
def get_student_assignment_detail(request: Request, student_id: int, assignment_id: int, db: Session = Depends(get_db)):
    row = db.query(StudentAssignment).filter(
        StudentAssignment.id == int(assignment_id),
        StudentAssignment.student_id == int(student_id),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return {
        "request_id": request.state.request_id,
        "data": {
            "id": int(row.id),
            "student_id": int(row.student_id),
            "classroom_id": int(row.classroom_id),
            "topic_id": int(row.topic_id) if row.topic_id else None,
            "document_id": int(row.document_id),
            "assignment_type": str(row.assignment_type),
            "student_level": str(row.student_level),
            "status": str(row.status),
            "content_json": row.content_json if isinstance(row.content_json, dict) else {},
            "due_date": row.due_date.isoformat() if row.due_date else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        },
        "error": None,
    }


@router.post("/lms/students/{student_id}/assignments/{assignment_id}/complete")
def complete_student_assignment(request: Request, student_id: int, assignment_id: int, db: Session = Depends(get_db)):
    row = db.query(StudentAssignment).filter(
        StudentAssignment.id == int(assignment_id),
        StudentAssignment.student_id == int(student_id),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found")

    row.status = "completed"
    row.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)

    return {
        "request_id": request.state.request_id,
        "data": {
            "id": int(row.id),
            "status": str(row.status),
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        },
        "error": None,
    }
