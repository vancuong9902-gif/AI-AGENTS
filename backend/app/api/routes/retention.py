from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.retention import (
    RetentionDueListOut,
    RetentionGenerateRequest,
    RetentionScheduleCreateRequest,
    RetentionScheduleOut,
    RetentionSubmitOut,
    RetentionSubmitRequest,
)
from app.services.retention_service import (
    create_retention_schedules,
    generate_retention_quiz,
    list_retention_schedules,
    submit_retention_quiz,
)

router = APIRouter(tags=["retention"])


@router.get("/retention/due", response_model=RetentionDueListOut)
def retention_due(request: Request, user_id: int, include_upcoming: bool = True, db: Session = Depends(get_db)):
    data = list_retention_schedules(db, user_id=int(user_id), include_upcoming=bool(include_upcoming))
    safe = jsonable_encoder(
        {
            "user_id": int(user_id),
            "now_utc": data.get("now_utc"),
            "due": data.get("due") or [],
            "upcoming": data.get("upcoming") or [],
        }
    )
    return safe


@router.post("/retention/schedule", response_model=dict)
def retention_schedule_create(request: Request, payload: RetentionScheduleCreateRequest, db: Session = Depends(get_db)):
    out = create_retention_schedules(
        db,
        user_id=int(payload.user_id),
        topic_id=int(payload.topic_id),
        baseline_score_percent=int(payload.baseline_score_percent or 0),
        intervals_days=list(payload.intervals_days or [1, 7, 30]),
        source_attempt_id=int(payload.source_attempt_id) if payload.source_attempt_id is not None else None,
        source_quiz_set_id=int(payload.source_quiz_set_id) if payload.source_quiz_set_id is not None else None,
    )
    return jsonable_encoder(out)


@router.post("/retention/{schedule_id}/generate", response_model=dict)
def retention_generate(request: Request, schedule_id: int, payload: RetentionGenerateRequest, db: Session = Depends(get_db)):
    data = generate_retention_quiz(
        db,
        schedule_id=int(schedule_id),
        user_id=int(payload.user_id),
        language=str(payload.language or "vi"),
        difficulty=str(payload.difficulty) if payload.difficulty else None,
    )
    safe = jsonable_encoder(
        {
            "schedule": data.get("schedule"),
            "quiz": data.get("quiz"),
        }
    )
    return safe


@router.post("/retention/{schedule_id}/submit", response_model=RetentionSubmitOut)
def retention_submit(request: Request, schedule_id: int, payload: RetentionSubmitRequest, db: Session = Depends(get_db)):
    answers = [a.model_dump() for a in (payload.answers or [])]
    data = submit_retention_quiz(
        db,
        schedule_id=int(schedule_id),
        user_id=int(payload.user_id),
        duration_sec=int(payload.duration_sec or 0),
        answers=answers,
    )
    safe = jsonable_encoder(
        {
            "schedule": data.get("schedule"),
            "graded": data.get("graded"),
            "retention_metrics": data.get("retention_metrics") or {},
            "delayed_reward": data.get("delayed_reward") or {},
        }
    )
    return safe
