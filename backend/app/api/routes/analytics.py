from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_teacher, require_user
from app.db.session import get_db
from app.models.attempt import Attempt
from app.models.classroom import Classroom, ClassroomMember
from app.models.quiz_set import QuizSet
from app.models.study_session import StudySession
from app.models.user import User
from app.models.session import Session as LearningSession
from app.schemas.analytics import AnalyticsWeightsIn
from app.services.analytics_service import (
    compute_composite_analytics,
    dashboard_topics,
    get_analytics_history,
    set_analytics_weights,
    update_profile_analytics,
)

router = APIRouter(tags=["analytics"])


def _to_pct(value: float) -> float:
    return round(max(0.0, min(100.0, float(value or 0.0))), 2)


def _score_ranges(scores: list[float]) -> list[dict]:
    bins = [
        {"range": "0-20", "count": 0},
        {"range": "21-40", "count": 0},
        {"range": "41-60", "count": 0},
        {"range": "61-80", "count": 0},
        {"range": "81-100", "count": 0},
    ]
    for score in scores:
        s = _to_pct(score)
        if s <= 20:
            bins[0]["count"] += 1
        elif s <= 40:
            bins[1]["count"] += 1
        elif s <= 60:
            bins[2]["count"] += 1
        elif s <= 80:
            bins[3]["count"] += 1
        else:
            bins[4]["count"] += 1
    return bins


@router.get("/analytics/composite")
def composite(
    user_id: int,
    document_id: int | None = None,
    window_days: int = 14,
    persist: bool = True,
    db: Session = Depends(get_db),
):
    """Compute composite analytics.

    If persist=true (default), the metrics are also stored into LearnerProfile.mastery_json
    under keys: analytics, analytics_history, topic_mastery_history.
    """

    if persist:
        return update_profile_analytics(db, user_id=int(user_id), document_id=document_id, window_days=int(window_days), reason="dashboard")
    return compute_composite_analytics(db, user_id=int(user_id), document_id=document_id, window_days=int(window_days))


@router.post("/analytics/weights")
def set_weights(payload: AnalyticsWeightsIn, db: Session = Depends(get_db)):
    w = set_analytics_weights(
        db,
        user_id=int(payload.user_id),
        weights={
            "w1_knowledge": float(payload.w1_knowledge),
            "w2_improvement": float(payload.w2_improvement),
            "w3_engagement": float(payload.w3_engagement),
            "w4_retention": float(payload.w4_retention),
        },
    )
    return {"user_id": int(payload.user_id), "weights": w}


@router.get("/analytics/dashboard")
def dashboard(
    user_id: int,
    document_id: int | None = None,
    window_days: int = 14,
    db: Session = Depends(get_db),
):
    analytics = update_profile_analytics(db, user_id=int(user_id), document_id=document_id, window_days=int(window_days), reason="dashboard")

    topics = []
    if document_id is not None:
        topics = dashboard_topics(db, user_id=int(user_id), document_id=int(document_id))

    return {
        "user_id": int(user_id),
        "document_id": int(document_id) if document_id is not None else None,
        "window_days": int(window_days),
        "analytics": {k: v for k, v in analytics.items() if k != "debug"},
        "topics": topics,
        "activity": (analytics.get("debug") or {}).get("engagement") if isinstance(analytics.get("debug"), dict) else {},
    }


@router.get("/analytics/history")
def history(
    user_id: int,
    document_id: int | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    """Return persisted analytics_history points.

    This endpoint does not recompute analytics. Call /analytics/composite or /analytics/dashboard
    if you need a fresh point appended first.
    """

    return {
        "user_id": int(user_id),
        "document_id": int(document_id) if document_id is not None else None,
        "points": get_analytics_history(db, user_id=int(user_id), document_id=document_id, limit=int(limit)),
    }


@router.get("/analytics/learning-hours")
def learning_hours(user_id: int, days: int = 30, db: Session = Depends(get_db)):
    days = max(1, min(365, int(days)))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    sessions = (
        db.query(LearningSession.started_at, LearningSession.ended_at)
        .filter(LearningSession.user_id == int(user_id), LearningSession.started_at >= cutoff)
        .all()
    )
    by_date: dict[str, float] = {}
    for started_at, ended_at in sessions:
        if not started_at or not ended_at:
            continue
        s_at = started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
        e_at = ended_at if ended_at.tzinfo else ended_at.replace(tzinfo=timezone.utc)
        hours = max(0.0, (e_at - s_at).total_seconds() / 3600.0)
        key = s_at.date().isoformat()
        by_date[key] = by_date.get(key, 0.0) + hours
    return [{"date": d, "hours": round(h, 2)} for d, h in sorted(by_date.items())]


@router.get("/teacher/classrooms/{classroom_id}/analytics")
def teacher_classroom_analytics(
    classroom_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    classroom = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    if not classroom or int(classroom.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=404, detail="Classroom not found")

    student_ids = [
        int(row[0])
        for row in db.query(ClassroomMember.user_id)
        .filter(ClassroomMember.classroom_id == int(classroom_id))
        .all()
    ]
    if not student_ids:
        return {
            "total_students": 0,
            "avg_score": 0.0,
            "completion_rate": 0.0,
            "support_needed": 0,
            "score_distribution": _score_ranges([]),
            "level_distribution": {"beginner": 0, "intermediate": 0, "advanced": 0},
            "study_time_weekly": [],
            "topic_mastery": [],
            "progress_comparison": [],
        }

    attempts = (
        db.query(Attempt, QuizSet)
        .join(QuizSet, QuizSet.id == Attempt.quiz_set_id)
        .filter(Attempt.user_id.in_(student_ids))
        .all()
    )

    latest_by_student: dict[int, float] = {}
    placement_by_student: dict[int, float] = {}
    final_by_student: dict[int, float] = {}
    topic_scores: dict[str, list[float]] = {}
    completed_students: set[int] = set()

    for attempt, quiz in attempts:
        uid = int(attempt.user_id)
        score = _to_pct(float(attempt.score_percent or 0))
        latest_by_student[uid] = score
        kind = str(quiz.kind or "").lower()
        if kind in {"diagnostic_pre", "placement"}:
            placement_by_student[uid] = score
        if kind in {"diagnostic_post", "final", "final_exam"}:
            final_by_student[uid] = score
            completed_students.add(uid)

        for item in (attempt.breakdown_json or []):
            topic = str(item.get("topic") or item.get("name") or "Khác")
            pct = item.get("percent")
            if pct is None:
                continue
            topic_scores.setdefault(topic, []).append(_to_pct(float(pct)))

    latest_scores = [latest_by_student.get(uid, 0.0) for uid in student_ids]
    avg_score = round(sum(latest_scores) / max(1, len(latest_scores)), 2)
    completion_rate = round(len(completed_students) / max(1, len(student_ids)) * 100.0, 2)
    support_needed = len([s for s in latest_scores if s < 50])

    level_distribution = {"beginner": 0, "intermediate": 0, "advanced": 0}
    for score in latest_scores:
        if score < 50:
            level_distribution["beginner"] += 1
        elif score < 80:
            level_distribution["intermediate"] += 1
        else:
            level_distribution["advanced"] += 1

    names = {
        int(uid): str(name or f"Student #{uid}")
        for uid, name in db.query(User.id, User.full_name).filter(User.id.in_(student_ids)).all()
    }
    progress_comparison = [
        {
            "student_name": names.get(uid, f"Student #{uid}"),
            "placement": placement_by_student.get(uid, 0.0),
            "final": final_by_student.get(uid, latest_by_student.get(uid, 0.0)),
        }
        for uid in student_ids
    ]

    since = datetime.now(timezone.utc).date() - timedelta(days=6)
    weekly_map = { (since + timedelta(days=i)).isoformat(): 0.0 for i in range(7) }
    sessions = (
        db.query(StudySession)
        .filter(StudySession.student_id.in_(student_ids), StudySession.created_at >= datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc))
        .all()
    )
    for s in sessions:
        key = (s.started_at or s.created_at).date().isoformat()
        if key not in weekly_map:
            continue
        hours = float(s.duration_seconds or 0) / 3600.0
        if hours <= 0 and s.started_at and s.ended_at:
            hours = max(0.0, (s.ended_at - s.started_at).total_seconds() / 3600.0)
        weekly_map[key] += hours

    topic_mastery = [
        {"topic": topic, "avg_score": round(sum(values) / len(values), 2)}
        for topic, values in topic_scores.items()
        if values
    ]
    topic_mastery.sort(key=lambda row: row["avg_score"], reverse=True)

    return {
        "total_students": len(student_ids),
        "avg_score": avg_score,
        "completion_rate": completion_rate,
        "support_needed": support_needed,
        "score_distribution": _score_ranges(latest_scores),
        "level_distribution": level_distribution,
        "study_time_weekly": [{"date": d, "hours": round(h, 2)} for d, h in weekly_map.items()],
        "topic_mastery": topic_mastery,
        "progress_comparison": progress_comparison,
    }


@router.get("/student/analytics")
def student_analytics(
    db: Session = Depends(get_db),
    student: User = Depends(require_user),
):
    attempts = (
        db.query(Attempt, QuizSet)
        .join(QuizSet, QuizSet.id == Attempt.quiz_set_id)
        .filter(Attempt.user_id == int(student.id))
        .order_by(Attempt.created_at.asc())
        .all()
    )

    score_history = [
        {
            "date": (attempt.created_at.date().isoformat() if attempt.created_at else datetime.now(timezone.utc).date().isoformat()),
            "score": _to_pct(float(attempt.score_percent or 0)),
            "exam_type": str(quiz.kind or "quiz"),
        }
        for attempt, quiz in attempts
    ]

    topic_acc: dict[str, list[float]] = {}
    for attempt, _quiz in attempts:
        for item in (attempt.breakdown_json or []):
            topic = str(item.get("topic") or item.get("name") or "Khác")
            pct = item.get("percent")
            if pct is None:
                continue
            topic_acc.setdefault(topic, []).append(_to_pct(float(pct)))

    topic_progress = []
    for topic, values in topic_acc.items():
        avg = round(sum(values) / len(values), 2)
        topic_progress.append({"topic": topic, "score": avg, "completed": avg >= 60})

    overall_progress = round((sum([row["score"] for row in topic_progress]) / max(1, len(topic_progress))), 2)

    week_start = datetime.now(timezone.utc).date() - timedelta(days=6)
    sessions = (
        db.query(StudySession)
        .filter(
            StudySession.student_id == int(student.id),
            StudySession.created_at >= datetime.combine(week_start, datetime.min.time(), tzinfo=timezone.utc),
        )
        .all()
    )
    study_hours = 0.0
    for s in sessions:
        hours = float(s.duration_seconds or 0) / 3600.0
        if hours <= 0 and s.started_at and s.ended_at:
            hours = max(0.0, (s.ended_at - s.started_at).total_seconds() / 3600.0)
        study_hours += hours

    return {
        "overall_progress": overall_progress,
        "score_history": score_history,
        "topic_progress": topic_progress,
        "study_hours_this_week": round(study_hours, 2),
    }
