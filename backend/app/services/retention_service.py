from __future__ import annotations

import datetime as _dt
import math
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.learner_profile import LearnerProfile
from app.models.document_topic import DocumentTopic
from app.models.retention_schedule import RetentionSchedule
from app.services.user_service import ensure_user_exists
from app.services.agent_service import generate_exam, grade_exam
from app.services.adaptive_policy_service import apply_feedback
from app.services.retention_scheduler import create_retention_schedules, list_retention_schedules


def _now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


# ==========================================================
# Retention execution (generate -> grade -> delayed reward)
# ==========================================================


def generate_retention_quiz(
    db: Session,
    *,
    schedule_id: int,
    user_id: int,
    language: str,
    difficulty: Optional[str] = None,
) -> Dict[str, Any]:
    ensure_user_exists(db, int(user_id), role="student")

    sch = (
        db.query(RetentionSchedule)
        .filter(RetentionSchedule.id == int(schedule_id))
        .filter(RetentionSchedule.user_id == int(user_id))
        .first()
    )
    if not sch:
        raise HTTPException(status_code=404, detail="Retention schedule not found")
    if sch.status != "pending":
        raise HTTPException(status_code=409, detail="Schedule is not pending")

    topic = db.query(DocumentTopic).filter(DocumentTopic.id == int(sch.topic_id)).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    rag_query = f"Ôn tập ghi nhớ sau {int(sch.interval_days)} ngày: {str(topic.title or '')}"
    gen = generate_exam(
        db,
        user_id=int(user_id),
        kind="retention_check",
        document_ids=[int(topic.document_id)],
        topics=[str(topic.title or "")],
        language=str(language or "vi"),
        rag_query=rag_query,
    )

    sch.retention_quiz_set_id = int(gen.get("quiz_id"))
    db.add(sch)
    db.commit()

    return {"schedule": sch, "quiz": gen}


def _fit_forgetting_lambda(baseline: float, points: List[Tuple[int, float]]) -> Dict[str, Any]:
    baseline = _clip(baseline, 1e-6, 1.0)
    vals = []
    for d, s in points:
        if d <= 0:
            continue
        s = _clip(s, 1e-6, 1.0)
        vals.append(-math.log(s / baseline) / float(d))
    if not vals:
        return {"lambda": None, "half_life_days": None}
    lam = float(sum(vals) / len(vals))
    lam = _clip(lam, 1e-6, 10.0)
    half = math.log(2.0) / lam
    return {"lambda": lam, "half_life_days": half}


def _retention_reward(
    *,
    baseline_score_percent: int,
    retention_score_percent: int,
    interval_days: int,
) -> Dict[str, Any]:
    baseline = _clip(float(baseline_score_percent) / 100.0, 0.0, 1.0)
    ret = _clip(float(retention_score_percent) / 100.0, 0.0, 1.0)
    delta = ret - baseline

    w = math.log(1.0 + float(max(1, interval_days))) / math.log(1.0 + 30.0)
    r = w * (0.70 * delta + 0.30 * (ret - 0.50))
    r = _clip(1.8 * r, -1.0, 1.0)

    return {
        "baseline": baseline,
        "retention": ret,
        "delta": delta,
        "interval_days": int(interval_days),
        "weight": float(round(w, 4)),
        "reward": float(round(r, 4)),
    }


def submit_retention_quiz(
    db: Session,
    *,
    schedule_id: int,
    user_id: int,
    duration_sec: int,
    answers: List[Dict[str, Any]],
    policy_alpha: float = 0.25,
    policy_gamma: float = 0.95,
) -> Dict[str, Any]:
    ensure_user_exists(db, int(user_id), role="student")

    sch = (
        db.query(RetentionSchedule)
        .filter(RetentionSchedule.id == int(schedule_id))
        .filter(RetentionSchedule.user_id == int(user_id))
        .first()
    )
    if not sch:
        raise HTTPException(status_code=404, detail="Retention schedule not found")
    if sch.status != "pending":
        raise HTTPException(status_code=409, detail="Schedule is not pending")
    if not sch.retention_quiz_set_id:
        raise HTTPException(status_code=409, detail="Retention quiz not generated")

    graded = grade_exam(
        db,
        quiz_id=int(sch.retention_quiz_set_id),
        user_id=int(user_id),
        duration_sec=int(duration_sec or 0),
        answers=answers,
    )

    sch.retention_attempt_id = int(graded.get("attempt_id"))
    sch.status = "completed"
    sch.completed_at = _now_utc()

    db.add(sch)
    db.commit()
    db.refresh(sch)

    # Update retention curve in profile
    topic = db.query(DocumentTopic).filter(DocumentTopic.id == int(sch.topic_id)).first()
    topic_key = f"doc{int(topic.document_id)}:topic{int(topic.id)}" if topic else str(sch.topic_id)

    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == int(user_id)).first()
    mj = (profile.mastery_json if profile else {}) or {}
    retention = mj.setdefault("retention", {})
    series = retention.setdefault(topic_key, {"baseline": int(sch.baseline_score_percent), "points": []})
    pts = series.get("points") if isinstance(series.get("points"), list) else []
    pts.append({"days": int(sch.interval_days), "score_percent": int(graded.get("score_percent") or 0), "ts": _now_utc().isoformat()})
    pts = pts[-20:]
    series["points"] = pts

    baseline = _clip(float(series.get("baseline", sch.baseline_score_percent)) / 100.0, 0.0, 1.0)
    fitted = _fit_forgetting_lambda(baseline, [(int(p.get("days")), _clip(float(p.get("score_percent", 0)) / 100.0, 0.0, 1.0)) for p in pts])

    retention_models = mj.setdefault("retention_models", {})
    retention_models[topic_key] = {**fitted, "updated_at": _now_utc().isoformat()}

    if profile:
        profile.mastery_json = mj
        db.add(profile)
        db.commit()

    # Delayed reward: attribute to stored origin decision if available.
    reward_info = _retention_reward(
        baseline_score_percent=int(sch.baseline_score_percent or 0),
        retention_score_percent=int(graded.get("score_percent") or 0),
        interval_days=int(sch.interval_days or 1),
    )

    delayed = {"applied": False, "reason": "missing_origin", "debug": reward_info}

    if sch.origin_action and sch.origin_policy_type and isinstance(sch.origin_state_json, dict) and sch.origin_state_json:
        try:
            fb = apply_feedback(
                db,
                user_id=int(user_id),
                policy_type=str(sch.origin_policy_type),  # type: ignore[arg-type]
                state=dict(sch.origin_state_json),
                action=str(sch.origin_action),  # type: ignore[arg-type]
                reward=float(reward_info.get("reward")),
                attempt_id=None,
                next_state=None,
                alpha=float(policy_alpha),
                gamma=float(policy_gamma),
            )
            delayed = {
                "applied": True,
                "origin": {"policy_type": sch.origin_policy_type, "action": sch.origin_action},
                "policy_update": fb,
                "debug": reward_info,
            }
        except Exception as e:
            delayed = {"applied": False, "reason": str(e), "debug": reward_info}

    

    # Composite analytics refresh (retention term changes after schedule completion).
    try:
        from app.services.analytics_service import update_profile_analytics

        update_profile_analytics(db, user_id=int(user_id), document_id=None, window_days=14, reason='retention')
    except Exception:
        pass

    return {
        "schedule": sch,
        "graded": graded,
        "retention_metrics": {"topic_key": topic_key, **reward_info, **fitted},
        "delayed_reward": delayed,
    }
