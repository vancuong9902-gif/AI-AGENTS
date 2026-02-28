from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.agent import (
    AgentPhase1Out,
    EntryTestGenerateRequest,
    EntryTestGenerateOut,
    EntryTestSubmitRequest,
    EntryTestSubmitOut,
    FinalExamGenerateRequest,
    FinalExamGenerateOut,
    FinalExamSubmitRequest,
    FinalExamSubmitOut,
    TopicExercisesGenerateRequest,
    TopicExercisesGenerateOut,
    TopicExercisesSubmitRequest,
    TopicExercisesSubmitOut,
)
from app.services.agent_service import (
    build_phase1_document_analysis,
    generate_exam,
    grade_exam,
    final_exam_analytics,
    generate_topic_exercises,
    postprocess_topic_attempt,
)
from app.services.lms_service import _send_final_report_to_teacher
from app.models.diagnostic_attempt import DiagnosticAttempt
from app.models.learning_plan import LearningPlan, LearningPlanTaskCompletion


router = APIRouter(tags=["agent"])


def _count_plan_tasks(plan_json: Dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    days = plan_json.get("days") if isinstance(plan_json, dict) else []
    if not isinstance(days, list):
        return 0, []

    total = 0
    indexed: list[dict[str, Any]] = []
    for day_idx, day in enumerate(days, start=1):
        tasks = day.get("tasks") if isinstance(day, dict) else []
        if not isinstance(tasks, list):
            tasks = []
        for task_idx, task in enumerate(tasks, start=1):
            total += 1
            indexed.append(
                {
                    "day_index": int(day.get("day_index") or day_idx) if isinstance(day, dict) else day_idx,
                    "task_index": task_idx,
                    "day_title": str(day.get("title") or f"Ngày {day_idx}") if isinstance(day, dict) else f"Ngày {day_idx}",
                    "task_title": str((task or {}).get("title") or f"Nhiệm vụ {task_idx}") if isinstance(task, dict) else f"Nhiệm vụ {task_idx}",
                }
            )
    return total, indexed


def _final_exam_prerequisite_snapshot(db: Session, user_id: int) -> dict[str, Any]:
    # Điều kiện (1): đã có bài chẩn đoán đầu vào đã chấm.
    has_graded_diagnostic_pre = (
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
        .filter(LearningPlan.user_id == int(user_id))
        .order_by(LearningPlan.created_at.desc())
        .first()
    )
    total_tasks = 0
    completed_tasks = 0
    remaining_lessons: list[dict[str, Any]] = []

    if latest_plan:
        total_tasks, indexed = _count_plan_tasks(latest_plan.plan_json or {})
        done_rows = (
            db.query(LearningPlanTaskCompletion.day_index, LearningPlanTaskCompletion.task_index)
            .filter(
                and_(
                    LearningPlanTaskCompletion.plan_id == int(latest_plan.id),
                    LearningPlanTaskCompletion.completed.is_(True),
                )
            )
            .all()
        )
        done_set = {(int(r.day_index), int(r.task_index)) for r in done_rows}
        completed_tasks = len(done_set)
        for item in indexed:
            key = (int(item["day_index"]), int(item["task_index"]))
            if key in done_set:
                continue
            remaining_lessons.append(
                {
                    "day_index": int(item["day_index"]),
                    "task_index": int(item["task_index"]),
                    "title": f"{item['day_title']} - {item['task_title']}",
                    "link": f"/agent-flow#topic-day-{int(item['day_index'])}",
                }
            )

    progress = round((completed_tasks / total_tasks) * 100, 1) if total_tasks > 0 else 0.0

    return {
        "has_graded_diagnostic_pre": bool(has_graded_diagnostic_pre),
        "completed_tasks": int(completed_tasks),
        "total_tasks": int(total_tasks),
        "progress": progress,
        "required": 70,
        "remaining_lessons": remaining_lessons,
    }


@router.get("/agent/documents/{document_id}/phase1", response_model=AgentPhase1Out)
def phase1_document_analysis(
    request: Request,
    document_id: int,
    include_llm: int = 1,
    max_topics: int = 40,
    db: Session = Depends(get_db),
):
    data = build_phase1_document_analysis(db, document_id=int(document_id), include_llm=bool(include_llm), max_topics=int(max_topics))
    safe = jsonable_encoder(data)
    return safe


@router.post("/agent/entry-test/generate", response_model=EntryTestGenerateOut)
def entry_test_generate(request: Request, payload: EntryTestGenerateRequest, db: Session = Depends(get_db)):
    data = generate_exam(
        db,
        user_id=int(payload.user_id),
        kind="entry_test",
        document_ids=[int(x) for x in (payload.document_ids or [])],
        topics=[str(x) for x in (payload.topics or [])],
        language=str(payload.language or "vi"),
        rag_query=(payload.rag_query or None),
    )
    out = {
        "quiz_id": int(data["quiz_id"]),
        "kind": str(data["kind"]),
        "title": "Entry Test",
        "questions": data["questions"],
    }
    safe = jsonable_encoder(out)
    return safe


@router.post("/agent/entry-test/{quiz_id}/submit", response_model=EntryTestSubmitOut)
def entry_test_submit(request: Request, quiz_id: int, payload: EntryTestSubmitRequest, db: Session = Depends(get_db)):
    answers = [a.model_dump() for a in (payload.answers or [])]
    data = grade_exam(
        db,
        quiz_id=int(quiz_id),
        user_id=int(payload.user_id),
        duration_sec=int(payload.duration_sec or 0),
        answers=answers,
    )
    safe = jsonable_encoder(data)
    return safe


@router.post("/agent/final-exam/generate", response_model=FinalExamGenerateOut)
def final_exam_generate(request: Request, payload: FinalExamGenerateRequest, db: Session = Depends(get_db)):
    prereq = _final_exam_prerequisite_snapshot(db, int(payload.user_id))
    if (not prereq["has_graded_diagnostic_pre"]) or (float(prereq["progress"]) < float(prereq["required"])):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "PREREQUISITE_NOT_MET",
                "detail": (
                    "Bạn cần hoàn thành 70% bài học được giao trước khi thi cuối kỳ. "
                    f"Hiện tại bạn đã hoàn thành {prereq['progress']}%."
                ),
                "progress": prereq["progress"],
                "required": prereq["required"],
                "remaining_lessons": prereq["remaining_lessons"],
                "has_graded_diagnostic_pre": prereq["has_graded_diagnostic_pre"],
            },
        )

    data = generate_exam(
        db,
        user_id=int(payload.user_id),
        kind="final_exam",
        document_ids=[int(x) for x in (payload.document_ids or [])],
        topics=[str(x) for x in (payload.topics or [])],
        language=str(payload.language or "vi"),
        rag_query=(payload.rag_query or None),
    )
    out = {
        "quiz_id": int(data["quiz_id"]),
        "kind": str(data["kind"]),
        "title": "Final Exam",
        "questions": data["questions"],
    }
    safe = jsonable_encoder(out)
    return safe


@router.post("/agent/final-exam/{quiz_id}/submit", response_model=FinalExamSubmitOut)
def final_exam_submit(request: Request, quiz_id: int, payload: FinalExamSubmitRequest, db: Session = Depends(get_db)):
    answers = [a.model_dump() for a in (payload.answers or [])]
    data = grade_exam(
        db,
        quiz_id=int(quiz_id),
        user_id=int(payload.user_id),
        duration_sec=int(payload.duration_sec or 0),
        answers=answers,
    )
    analytics = final_exam_analytics(data.get("breakdown") or [])
    data["analytics"] = analytics
    try:
        _send_final_report_to_teacher(
            db,
            student_id=payload.user_id,
            quiz_id=quiz_id,
            analytics=analytics,
            breakdown=data.get("breakdown") or [],
        )
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(f"push_report failed: {e}")
    safe = jsonable_encoder(data)
    return safe


@router.post("/agent/topic-exercises/generate", response_model=TopicExercisesGenerateOut)
def topic_exercises_generate(request: Request, payload: TopicExercisesGenerateRequest, db: Session = Depends(get_db)):
    data = generate_topic_exercises(
        db,
        user_id=int(payload.user_id),
        topic_id=int(payload.topic_id),
        language=str(payload.language or "vi"),
        difficulty=(str(payload.difficulty) if payload.difficulty else None),
    )
    safe = jsonable_encoder(data)
    return safe


@router.post("/agent/topic-exercises/{quiz_id}/submit", response_model=TopicExercisesSubmitOut)
def topic_exercises_submit(request: Request, quiz_id: int, payload: TopicExercisesSubmitRequest, db: Session = Depends(get_db)):
    answers = [a.model_dump() for a in (payload.answers or [])]
    graded = grade_exam(
        db,
        quiz_id=int(quiz_id),
        user_id=int(payload.user_id),
        duration_sec=int(payload.duration_sec or 0),
        answers=answers,
    )
    data = postprocess_topic_attempt(
        db,
        user_id=int(payload.user_id),
        topic_id=int(payload.topic_id),
        quiz_id=int(quiz_id),
        attempt_payload=graded,
    )
    safe = jsonable_encoder(data)
    return safe
