from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.learner_profile import LearnerProfile
from app.models.document_topic import DocumentTopic
from app.models.retention_schedule import RetentionSchedule
from app.services.user_service import ensure_user_exists


def _now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def create_retention_schedules(
    db: Session,
    *,
    user_id: int,
    topic_id: int,
    baseline_score_percent: int,
    intervals_days: List[int],
    source_attempt_id: Optional[int] = None,
    source_quiz_set_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Create pending retention checks for a topic (idempotent best-effort)."""

    ensure_user_exists(db, int(user_id), role="student")

    topic = db.query(DocumentTopic).filter(DocumentTopic.id == int(topic_id)).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == int(user_id)).first()
    mj = (profile.mastery_json if profile else {}) or {}
    last_decision = ((mj.get("rl") or {}).get("last_decision") or {}) if isinstance(mj.get("rl"), dict) else {}

    created: List[RetentionSchedule] = []
    now = _now_utc()

    for d in sorted(set(int(x) for x in (intervals_days or []) if int(x) > 0))[:6]:
        due_at = now + _dt.timedelta(days=int(d))

        exists = (
            db.query(RetentionSchedule)
            .filter(RetentionSchedule.user_id == int(user_id))
            .filter(RetentionSchedule.topic_id == int(topic_id))
            .filter(RetentionSchedule.interval_days == int(d))
            .filter(RetentionSchedule.status == "pending")
            .first()
        )
        if exists:
            continue

        sch = RetentionSchedule(
            user_id=int(user_id),
            topic_id=int(topic_id),
            interval_days=int(d),
            due_at=due_at,
            status="pending",
            baseline_score_percent=int(max(0, min(100, int(baseline_score_percent or 0)))),
            source_attempt_id=int(source_attempt_id) if source_attempt_id is not None else None,
            source_quiz_set_id=int(source_quiz_set_id) if source_quiz_set_id is not None else None,
            origin_policy_type=str(last_decision.get("policy_type") or "")[:50] or None,
            origin_action=str(last_decision.get("action") or "")[:64] or None,
            origin_state_json=last_decision.get("state") if isinstance(last_decision.get("state"), dict) else {},
        )
        db.add(sch)
        db.flush()
        created.append(sch)

    db.commit()

    return {
        "user_id": int(user_id),
        "topic_id": int(topic_id),
        "created": [int(s.id) for s in created],
        "count": int(len(created)),
    }


def list_retention_schedules(
    db: Session,
    *,
    user_id: int,
    include_upcoming: bool = True,
    upcoming_limit: int = 20,
) -> Dict[str, Any]:
    ensure_user_exists(db, int(user_id), role="student")
    now = _now_utc()

    due = (
        db.query(RetentionSchedule)
        .filter(RetentionSchedule.user_id == int(user_id))
        .filter(RetentionSchedule.status == "pending")
        .filter(RetentionSchedule.due_at <= now)
        .order_by(RetentionSchedule.due_at.asc())
        .all()
    )

    upcoming = []
    if include_upcoming:
        upcoming = (
            db.query(RetentionSchedule)
            .filter(RetentionSchedule.user_id == int(user_id))
            .filter(RetentionSchedule.status == "pending")
            .filter(RetentionSchedule.due_at > now)
            .order_by(RetentionSchedule.due_at.asc())
            .limit(int(max(1, min(200, upcoming_limit))))
            .all()
        )

    return {
        "user_id": int(user_id),
        "now_utc": now.isoformat(),
        "due": due,
        "upcoming": upcoming,
    }
