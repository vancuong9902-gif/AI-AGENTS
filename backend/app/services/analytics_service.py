from __future__ import annotations

import datetime as _dt
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.attempt import Attempt
from app.models.document_topic import DocumentTopic
from app.models.learner_profile import LearnerProfile
from app.models.question import Question
from app.models.quiz_set import QuizSet
from app.models.retention_schedule import RetentionSchedule
from app.models.classroom import Classroom, ClassroomMember
from app.models.classroom_assessment import ClassroomAssessment
from app.models.user import User
from app.services.llm_service import chat_text, llm_available
from app.services.lms_service import classify_student_level, generate_class_narrative, score_breakdown
from app.services.vietnamese_font_fix import get_noto_sans_font_path


# ==========================================================
# Composite Analytics + Dashboard Metrics (Research Prototype)
#
# FinalScore = w1*Knowledge + w2*Improvement + w3*Engagement + w4*Retention
# + dropout prediction.
#
# Design goals:
#  - no extra labeled data required
#  - uses existing attempt logs + learner posterior + retention schedules
#  - explainable outputs (drivers for dropout risk)
#  - cheap to compute on-demand; optionally persisted in profile JSON
# ==========================================================


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _iso(dt: _dt.datetime) -> str:
    return dt.astimezone(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, float(x))))


def _sigmoid(x: float) -> float:
    # numerically stable-ish for our expected ranges
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _normalize_weights(w: Dict[str, float]) -> Dict[str, float]:
    s = float(sum(max(0.0, float(v)) for v in w.values()))
    if s <= 1e-9:
        return {k: 0.25 for k in ["w1_knowledge", "w2_improvement", "w3_engagement", "w4_retention"]}
    return {k: float(max(0.0, float(v)) / s) for k, v in w.items()}


def _parse_topic_mastery(mj: Dict[str, Any], *, document_id: Optional[int]) -> Dict[str, float]:
    tm = mj.get("topic_mastery") if isinstance(mj.get("topic_mastery"), dict) else {}
    out: Dict[str, float] = {}
    for k, v in (tm or {}).items():
        try:
            kk = str(k)
            if document_id is not None and not kk.startswith(f"doc{int(document_id)}:"):
                continue
            out[kk] = float(v)
        except Exception:
            continue
    return out


def compute_knowledge(mj: Dict[str, Any], *, document_id: Optional[int] = None) -> float:
    tm = _parse_topic_mastery(mj, document_id=document_id)
    vals = [v for k, v in tm.items() if k != "__global__" and isinstance(v, (int, float))]
    if vals:
        return _clip(sum(vals) / float(len(vals)), 0.0, 1.0)

    # fallback to last exam score if no mastery posterior yet
    try:
        last = float(mj.get("__last_exam_score_percent__") or 0.0)
        return _clip(last, 0.0, 1.0)
    except Exception:
        return 0.0


def _get_or_init_profile(db: Session, user_id: int) -> LearnerProfile:
    prof = db.query(LearnerProfile).filter(LearnerProfile.user_id == int(user_id)).first()
    if not prof:
        prof = LearnerProfile(user_id=int(user_id), level="beginner", mastery_json={})
        db.add(prof)
        db.commit()
        db.refresh(prof)
    return prof


def _time_quality(seconds_per_q: float) -> float:
    """Heuristic engagement proxy based on time per question.

    - too fast => guessing / low engagement
    - moderate => good
    - too slow => confusion / overload

    Returns in [0,1].
    """

    s = float(seconds_per_q)
    if s <= 0:
        return 0.0
    if s < 10:
        return 0.0
    if s < 20:
        return (s - 10.0) / 10.0  # 0..1
    if s <= 90:
        return 1.0
    if s <= 180:
        return 1.0 - 0.5 * ((s - 90.0) / 90.0)  # 1..0.5
    return 0.2


def compute_engagement(
    db: Session,
    *,
    user_id: int,
    window_days: int = 14,
) -> Tuple[float, Dict[str, Any]]:
    since = _utcnow() - _dt.timedelta(days=int(window_days))

    attempts: List[Attempt] = (
        db.query(Attempt)
        .filter(Attempt.user_id == int(user_id))
        .filter(Attempt.created_at >= since)
        .order_by(Attempt.created_at.desc())
        .limit(80)
        .all()
    )

    quiz_sets_count = (
        db.query(QuizSet)
        .filter(QuizSet.user_id == int(user_id))
        .filter(QuizSet.created_at >= since)
        .count()
    )

    attempts_count = len(attempts)
    days_active = sorted({(a.created_at.date() if a.created_at else None) for a in attempts if a.created_at})
    days_active = [d for d in days_active if d is not None]
    sessions_days = len(days_active)

    completion_rate = _clip(attempts_count / float(max(1, quiz_sets_count)), 0.0, 1.0)

    # time-on-task quality
    qs_ids = list({int(a.quiz_set_id) for a in attempts if a.quiz_set_id})
    q_counts: Dict[int, int] = {}
    if qs_ids:
        rows = (
            db.query(Question.quiz_set_id, func.count(Question.id))
            .filter(Question.quiz_set_id.in_(qs_ids))
            .group_by(Question.quiz_set_id)
            .all()
        )
        q_counts = {int(qid): int(cnt) for qid, cnt in rows}

    tq_vals: List[float] = []
    sec_per_q_vals: List[float] = []
    for a in attempts[:25]:
        qc = int(q_counts.get(int(a.quiz_set_id), 0) or 0)
        if qc <= 0:
            continue
        dur = int(a.duration_sec or 0)
        if dur <= 0:
            continue
        spq = float(dur) / float(qc)
        sec_per_q_vals.append(spq)
        tq_vals.append(_time_quality(spq))

    time_quality = float(sum(tq_vals) / len(tq_vals)) if tq_vals else 0.5

    # session regularity proxy
    session_term = _clip(sessions_days / 5.0, 0.0, 1.0)

    engagement = _clip(0.4 * session_term + 0.3 * completion_rate + 0.3 * time_quality, 0.0, 1.0)

    debug = {
        "window_days": int(window_days),
        "attempts_count": int(attempts_count),
        "quiz_sets_count": int(quiz_sets_count),
        "sessions_days": int(sessions_days),
        "completion_rate": round(float(completion_rate), 4),
        "time_quality": round(float(time_quality), 4),
        "avg_seconds_per_question": round(float(sum(sec_per_q_vals) / len(sec_per_q_vals)), 2) if sec_per_q_vals else None,
    }

    return engagement, debug


def compute_retention(
    db: Session,
    *,
    user_id: int,
    mj: Dict[str, Any],
    document_id: Optional[int] = None,
    window_days: int = 60,
) -> Tuple[float, Dict[str, Any]]:
    since = _utcnow() - _dt.timedelta(days=int(window_days))

    # Empirical: completed schedules within window
    schedules: List[RetentionSchedule] = (
        db.query(RetentionSchedule)
        .filter(RetentionSchedule.user_id == int(user_id))
        .filter(RetentionSchedule.status == "completed")
        .filter(RetentionSchedule.completed_at >= since)
        .order_by(RetentionSchedule.completed_at.desc())
        .limit(200)
        .all()
    )

    # Fetch attempt scores in batch
    attempt_ids = [int(s.retention_attempt_id) for s in schedules if s.retention_attempt_id]
    a_scores: Dict[int, int] = {}
    if attempt_ids:
        rows = db.query(Attempt.id, Attempt.score_percent).filter(Attempt.id.in_(attempt_ids)).all()
        a_scores = {int(i): int(sp or 0) for i, sp in rows}

    ratios: List[float] = []
    for s in schedules:
        if document_id is not None:
            # best-effort doc filter using topic_id -> DocumentTopic
            t = db.query(DocumentTopic.document_id).filter(DocumentTopic.id == int(s.topic_id)).first()
            if t and int(t[0]) != int(document_id):
                continue
        sp = int(a_scores.get(int(s.retention_attempt_id or 0), 0) or 0)
        base = int(s.baseline_score_percent or 0)
        if base > 0:
            ratios.append(_clip(sp / float(base), 0.0, 1.0))
        else:
            ratios.append(_clip(sp / 100.0, 0.0, 1.0))

    empirical = float(sum(ratios) / len(ratios)) if ratios else 0.0

    # Model-based: predicted ratio at 7d from lambda (exp(-lambda*7))
    pred_vals: List[float] = []
    rm = mj.get("retention_models") if isinstance(mj.get("retention_models"), dict) else {}
    for k, model in (rm or {}).items():
        try:
            kk = str(k)
            if document_id is not None and not kk.startswith(f"doc{int(document_id)}:"):
                continue
            lam = float((model or {}).get("lambda") or 0.0)
            if lam <= 0:
                continue
            pred_vals.append(_clip(math.exp(-lam * 7.0), 0.0, 1.0))
        except Exception:
            continue

    predicted_7d = float(sum(pred_vals) / len(pred_vals)) if pred_vals else 0.0

    retention = _clip(0.5 * empirical + 0.5 * predicted_7d, 0.0, 1.0)

    debug = {
        "window_days": int(window_days),
        "completed_schedules": int(len(schedules)),
        "empirical_mean_ratio": round(float(empirical), 4),
        "predicted_7d_ratio": round(float(predicted_7d), 4),
    }

    return retention, debug


def _history_append(mj: Dict[str, Any], *, key: str, point: Dict[str, Any], limit: int = 200) -> None:
    hist = mj.get(key)
    if not isinstance(hist, list):
        hist = []
        mj[key] = hist
    hist.append(point)
    mj[key] = hist[-limit:]


def _update_topic_mastery_history(mj: Dict[str, Any], *, ts: str, document_id: Optional[int]) -> None:
    tm = _parse_topic_mastery(mj, document_id=document_id)
    th = mj.get("topic_mastery_history")
    if not isinstance(th, dict):
        th = {}
        mj["topic_mastery_history"] = th

    for k, v in tm.items():
        series = th.get(k)
        if not isinstance(series, list):
            series = []
        series.append({"ts": ts, "mastery": round(float(v), 4)})
        th[k] = series[-30:]


def _slope_from_history(series: List[Dict[str, Any]], *, days: int = 7) -> Optional[float]:
    if not series or len(series) < 2:
        return None

    try:
        last = series[-1]
        t_last = _dt.datetime.fromisoformat(str(last["ts"]).replace("Z", "+00:00"))
        m_last = float(last.get("mastery", 0.0))
    except Exception:
        return None

    target = t_last - _dt.timedelta(days=int(days))
    best = None
    best_dt = None
    for p in series[:-1]:
        try:
            tt = _dt.datetime.fromisoformat(str(p["ts"]).replace("Z", "+00:00"))
            if tt <= target:
                best = p
                best_dt = tt
        except Exception:
            continue

    if not best:
        # fallback: earliest
        best = series[0]
        best_dt = _dt.datetime.fromisoformat(str(best["ts"]).replace("Z", "+00:00"))

    try:
        m0 = float(best.get("mastery", 0.0))
        dt_days = max(1e-6, (t_last - best_dt).total_seconds() / 86400.0)
        return (m_last - m0) / dt_days
    except Exception:
        return None


def predict_dropout(
    db: Session,
    *,
    user_id: int,
    mj: Dict[str, Any],
    knowledge: float,
    engagement: float,
) -> Dict[str, Any]:
    # Features from logs
    last_attempt = (
        db.query(Attempt)
        .filter(Attempt.user_id == int(user_id))
        .order_by(Attempt.created_at.desc())
        .first()
    )
    if last_attempt and last_attempt.created_at:
        inactivity_days = max(0.0, (_utcnow() - last_attempt.created_at).total_seconds() / 86400.0)
    else:
        inactivity_days = 999.0

    # Recent failures
    recent = (
        db.query(Attempt.score_percent)
        .filter(Attempt.user_id == int(user_id))
        .order_by(Attempt.created_at.desc())
        .limit(5)
        .all()
    )
    scores = [int(r[0] or 0) for r in recent]
    failure_rate = (sum(1 for s in scores if s < 60) / float(len(scores))) if scores else 0.0

    # Knowledge slope (from history)
    kh = mj.get("analytics_history") if isinstance(mj.get("analytics_history"), list) else []
    slope = None
    if len(kh) >= 2:
        # treat as global knowledge history
        try:
            series = [{"ts": p.get("ts"), "mastery": p.get("knowledge")} for p in kh if p.get("ts") and p.get("knowledge") is not None]
            series = [p for p in series if isinstance(p.get("mastery"), (int, float))]
            series.sort(key=lambda x: x["ts"])
            slope = _slope_from_history(series[-50:], days=7)
        except Exception:
            slope = None

    # Normalize features
    x_inactive = _clip(inactivity_days / 14.0, 0.0, 1.0)
    x_low_eng = _clip(1.0 - engagement, 0.0, 1.0)
    x_fail = _clip(failure_rate, 0.0, 1.0)
    # stall: slope < 0.002 per day (very slow gains)
    if slope is None:
        x_stall = 0.5
    else:
        x_stall = _clip((0.002 - float(slope)) / 0.004, 0.0, 1.0)

    # Logistic model (hand-tuned coefficients; replaceable with fitted model later)
    a0 = -1.2
    a1, a2, a3, a4 = 2.2, 1.6, 1.2, 1.0
    logit = a0 + a1 * x_inactive + a2 * x_low_eng + a3 * x_fail + a4 * x_stall
    risk = _clip(_sigmoid(logit), 0.0, 1.0)

    # Explain drivers by contribution
    drivers = [
        {"feature": "inactivity", "value": round(x_inactive, 4), "contribution": round(a1 * x_inactive, 4), "detail": f"days_since_last={round(inactivity_days, 2)}"},
        {"feature": "low_engagement", "value": round(x_low_eng, 4), "contribution": round(a2 * x_low_eng, 4), "detail": f"engagement={round(engagement, 3)}"},
        {"feature": "recent_failures", "value": round(x_fail, 4), "contribution": round(a3 * x_fail, 4), "detail": f"recent_scores={scores}"},
        {"feature": "learning_stall", "value": round(x_stall, 4), "contribution": round(a4 * x_stall, 4), "detail": f"knowledge_slope_7d={None if slope is None else round(float(slope), 5)}"},
    ]
    drivers.sort(key=lambda d: d["contribution"], reverse=True)

    if risk >= 0.7:
        band = "high"
    elif risk >= 0.4:
        band = "medium"
    else:
        band = "low"

    return {"risk": round(float(risk), 4), "band": band, "drivers": drivers[:4]}


def compute_composite_analytics(
    db: Session,
    *,
    user_id: int,
    document_id: Optional[int] = None,
    window_days: int = 14,
) -> Dict[str, Any]:
    prof = _get_or_init_profile(db, int(user_id))
    mj = dict(prof.mastery_json or {})

    scope = f"doc{int(document_id)}" if document_id is not None else "global"

    weights = mj.get("analytics_weights") if isinstance(mj.get("analytics_weights"), dict) else {}
    if not weights:
        weights = {"w1_knowledge": 0.45, "w2_improvement": 0.25, "w3_engagement": 0.15, "w4_retention": 0.15}
    weights = _normalize_weights(weights)

    knowledge = compute_knowledge(mj, document_id=document_id)

    # baseline/improvement
    baseline_block = mj.get("analytics_baseline") if isinstance(mj.get("analytics_baseline"), dict) else {}
    base_rec = baseline_block.get(scope) if isinstance(baseline_block.get(scope), dict) else None
    if not base_rec:
        base_k = knowledge
        baseline_block[scope] = {"ts": _iso(_utcnow()), "knowledge": round(float(base_k), 4), "source": "auto"}
        mj["analytics_baseline"] = baseline_block
        base_rec = baseline_block[scope]

    base_k = float(base_rec.get("knowledge", knowledge) or knowledge)
    denom = max(0.1, 1.0 - base_k)
    improvement = _clip((knowledge - base_k) / denom, 0.0, 1.0)

    engagement, engagement_debug = compute_engagement(db, user_id=int(user_id), window_days=int(window_days))
    retention, retention_debug = compute_retention(db, user_id=int(user_id), mj=mj, document_id=document_id)

    final_score = (
        weights["w1_knowledge"] * knowledge
        + weights["w2_improvement"] * improvement
        + weights["w3_engagement"] * engagement
        + weights["w4_retention"] * retention
    )
    final_score = _clip(final_score, 0.0, 1.0)

    dropout = predict_dropout(db, user_id=int(user_id), mj=mj, knowledge=knowledge, engagement=engagement)

    ts = _iso(_utcnow())
    analytics = {
        "scope": scope,
        "weights": weights,
        "knowledge": round(float(knowledge), 4),
        "improvement": round(float(improvement), 4),
        "engagement": round(float(engagement), 4),
        "retention": round(float(retention), 4),
        "final_score": round(float(final_score), 4),
        "dropout": dropout,
        "updated_at": ts,
        "debug": {"engagement": engagement_debug, "retention": retention_debug},
    }

    return analytics


def update_profile_analytics(
    db: Session,
    *,
    user_id: int,
    document_id: Optional[int] = None,
    window_days: int = 14,
    reason: str = "update",
) -> Dict[str, Any]:
    prof = _get_or_init_profile(db, int(user_id))
    mj = dict(prof.mastery_json or {})

    # entry_test baseline override: if the baseline was auto-created before the learner took the entry test,
    # we allow the entry test to become the canonical baseline for improvement.
    try:
        if 'entry_test' in str(reason) and isinstance(mj.get('analytics_baseline'), dict):
            scope = f"doc{int(document_id)}" if document_id is not None else 'global'
            rec = mj.get('analytics_baseline', {}).get(scope)
            if not isinstance(rec, dict) or str(rec.get('source') or 'auto') == 'auto':
                k0 = compute_knowledge(mj, document_id=document_id)
                mj.setdefault('analytics_baseline', {})[scope] = {
                    'ts': _iso(_utcnow()),
                    'knowledge': round(float(k0), 4),
                    'source': 'entry_test',
                }
    except Exception:
        pass

    analytics = compute_composite_analytics(db, user_id=int(user_id), document_id=document_id, window_days=int(window_days))

    # persist latest analytics
    mj["analytics"] = {k: v for k, v in analytics.items() if k != "debug"}

    # history
    _history_append(
        mj,
        key="analytics_history",
        point={
            "ts": analytics["updated_at"],
            "scope": analytics["scope"],
            "knowledge": analytics["knowledge"],
            "improvement": analytics["improvement"],
            "engagement": analytics["engagement"],
            "retention": analytics["retention"],
            "final_score": analytics["final_score"],
            "dropout_risk": (analytics.get("dropout") or {}).get("risk"),
            "reason": reason,
        },
        limit=300,
    )

    # topic mastery history for slopes / dashboard
    try:
        _update_topic_mastery_history(mj, ts=analytics["updated_at"], document_id=document_id)
    except Exception:
        pass

    prof.mastery_json = mj
    db.add(prof)
    db.commit()
    db.refresh(prof)

    return analytics


def get_analytics_history(
    db: Session,
    *,
    user_id: int,
    document_id: Optional[int] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Return persisted analytics_history points.

    This function is intentionally lightweight and does not recompute analytics.
    Use /analytics/composite or /analytics/dashboard to append a fresh point first.
    """

    prof = _get_or_init_profile(db, int(user_id))
    mj = dict(prof.mastery_json or {})
    hist = mj.get("analytics_history")
    if not isinstance(hist, list):
        return []

    scope = f"doc{int(document_id)}" if document_id is not None else "global"
    points: List[Dict[str, Any]] = []
    for p in hist:
        if not isinstance(p, dict):
            continue
        if str(p.get("scope") or "") != scope:
            continue
        points.append(p)

    try:
        points.sort(key=lambda x: str(x.get("ts") or ""))
    except Exception:
        pass

    if limit and int(limit) > 0:
        points = points[-int(limit) :]
    return points


def set_analytics_weights(db: Session, *, user_id: int, weights: Dict[str, float]) -> Dict[str, float]:
    prof = _get_or_init_profile(db, int(user_id))
    mj = dict(prof.mastery_json or {})

    w = {
        "w1_knowledge": float(weights.get("w1_knowledge", 0.45)),
        "w2_improvement": float(weights.get("w2_improvement", 0.25)),
        "w3_engagement": float(weights.get("w3_engagement", 0.15)),
        "w4_retention": float(weights.get("w4_retention", 0.15)),
    }
    w = _normalize_weights(w)
    mj["analytics_weights"] = w
    prof.mastery_json = mj
    db.add(prof)
    db.commit()
    return w


def dashboard_topics(
    db: Session,
    *,
    user_id: int,
    document_id: int,
) -> List[Dict[str, Any]]:
    prof = _get_or_init_profile(db, int(user_id))
    mj = dict(prof.mastery_json or {})

    # Build topic list
    topics: List[DocumentTopic] = (
        db.query(DocumentTopic)
        .filter(DocumentTopic.document_id == int(document_id))
        .order_by(DocumentTopic.topic_index.asc())
        .all()
    )

    tm = _parse_topic_mastery(mj, document_id=int(document_id))
    progress = mj.get("topic_progress") if isinstance(mj.get("topic_progress"), dict) else {}

    # retention due/completed counts
    pending_counts = dict(
        db.query(RetentionSchedule.topic_id, func.count(RetentionSchedule.id))
        .filter(RetentionSchedule.user_id == int(user_id))
        .filter(RetentionSchedule.status == "pending")
        .group_by(RetentionSchedule.topic_id)
        .all()
    )
    completed_60d_counts = dict(
        db.query(RetentionSchedule.topic_id, func.count(RetentionSchedule.id))
        .filter(RetentionSchedule.user_id == int(user_id))
        .filter(RetentionSchedule.status == "completed")
        .filter(RetentionSchedule.completed_at >= (_utcnow() - _dt.timedelta(days=60)))
        .group_by(RetentionSchedule.topic_id)
        .all()
    )

    # half-life from retention_models
    rm = mj.get("retention_models") if isinstance(mj.get("retention_models"), dict) else {}

    out: List[Dict[str, Any]] = []
    for t in topics:
        prefix = f"doc{int(document_id)}:topic{int(t.id)}"
        # match mastery key (which may include title)
        mval = None
        for k, v in tm.items():
            if str(k).startswith(prefix):
                mval = float(v)
                break
        if mval is None:
            mval = float(tm.get("__global__", 0.0) or 0.0)

        p = progress.get(str(t.id)) if isinstance(progress.get(str(t.id)), dict) else {}

        # half-life lookup (retention uses key without title)
        hl = None
        mdl = rm.get(prefix) if isinstance(rm.get(prefix), dict) else None
        if mdl and mdl.get("half_life_days") is not None:
            try:
                hl = float(mdl.get("half_life_days"))
            except Exception:
                hl = None

        out.append(
            {
                "topic_id": int(t.id),
                "topic_index": int(t.topic_index or 0),
                "title": str(t.title or ""),
                "mastery": round(float(mval), 4),
                "last_score_percent": int(p.get("last_score_percent")) if p.get("last_score_percent") is not None else None,
                "next_step": str(p.get("next_step")) if p.get("next_step") else None,
                "next_difficulty": str(p.get("next_difficulty")) if p.get("next_difficulty") else None,
                "retention_due_count": int(pending_counts.get(int(t.id), 0) or 0),
                "retention_completed_count_60d": int(completed_60d_counts.get(int(t.id), 0) or 0),
                "half_life_days": round(float(hl), 3) if hl is not None else None,
            }
        )

    return out


def generate_student_ai_assessment(db: Session, user_id: int, entry_attempt: Any, final_attempt: Any) -> str:
    user = db.query(User).filter(User.id == int(user_id)).first()
    name = str(getattr(user, "full_name", "") or f"Học sinh #{int(user_id)}")
    entry_score = float(getattr(entry_attempt, "score_percent", 0.0) or 0.0)
    final_score = float(getattr(final_attempt, "score_percent", 0.0) or 0.0)
    improvement = final_score - entry_score
    level = classify_student_level(int(round(final_score)))
    level_key = str(level["level_key"])

    final_breakdown = score_breakdown(getattr(final_attempt, "breakdown_json", []) or [])
    by_topic = final_breakdown.get("by_topic") if isinstance(final_breakdown.get("by_topic"), dict) else {}
    ranked_topics = sorted(
        [(str(t), float((s or {}).get("percent") or 0.0)) for t, s in by_topic.items()],
        key=lambda x: x[1],
    )
    weak_topics = [t for t, _ in ranked_topics[:2]]
    strong_topics = [t for t, _ in ranked_topics[-2:]][::-1]

    if not llm_available():
        fallback_map = {
            "gioi": "Em có nền tảng rất tốt và khả năng xử lý bài nâng cao khá ổn định.",
            "kha": "Em có năng lực học tập khá vững, cần tăng độ chắc ở một số phần kiến thức trọng tâm.",
            "trung_binh": "Em đã nắm được các ý cơ bản nhưng cần luyện thêm để tăng độ chính xác và tốc độ làm bài.",
            "yeu": "Em cần củng cố lại kiến thức nền và luyện theo lộ trình từng bước để tránh mất điểm ở câu cơ bản.",
        }
        progress_text = (
            f"Em đã tiến bộ {improvement:.1f} điểm so với bài đầu kỳ."
            if improvement >= 0
            else f"Điểm hiện tại giảm {abs(improvement):.1f} so với đầu kỳ, cần rà soát lại thói quen học tập."
        )
        weak_text = ", ".join(weak_topics) if weak_topics else "một vài chủ đề nền tảng"
        return (
            f"{name}: {fallback_map.get(level_key, fallback_map['trung_binh'])} "
            f"{progress_text} Điểm mạnh hiện tại là {', '.join(strong_topics) if strong_topics else 'các câu hỏi nhận biết-cơ bản'}. "
            f"Em nên tập trung ôn lại {weak_text} và luyện 20-30 phút mỗi ngày với bài tập tăng dần độ khó."
        )

    system_prompt = (
        "Bạn là giáo viên chủ nhiệm môn Toán. Viết nhận xét học sinh bằng tiếng Việt, 3-4 câu, ngắn gọn, tích cực và cụ thể. "
        "Bắt buộc đề cập: điểm mạnh, điểm yếu, sự tiến bộ, lời khuyên hành động cụ thể. Không bịa dữ liệu."
    )
    user_prompt = (
        f"Học sinh: {name}\n"
        f"Điểm entry: {entry_score:.1f}\n"
        f"Điểm final: {final_score:.1f}\n"
        f"Mức tiến bộ: {improvement:.1f}\n"
        f"Chủ đề mạnh: {', '.join(strong_topics) if strong_topics else 'chưa rõ'}\n"
        f"Chủ đề yếu: {', '.join(weak_topics) if weak_topics else 'chưa rõ'}"
    )
    try:
        return str(
            chat_text(
                [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.35,
                max_tokens=220,
            )
            or ""
        ).strip()
    except Exception:
        return f"{name} đã đạt {final_score:.1f} điểm và thay đổi {improvement:+.1f} điểm so với đầu kỳ. Em nên tập trung luyện theo các chủ đề yếu để cải thiện ổn định hơn."


def build_classroom_final_report(db: Session, classroom_id: int) -> Dict[str, Any]:
    classroom = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
    class_name = str(getattr(classroom, "name", "")) or f"Lớp {int(classroom_id)}"

    student_ids = [
        int(r[0])
        for r in db.query(ClassroomMember.user_id).filter(ClassroomMember.classroom_id == int(classroom_id)).all()
    ]
    assessment_ids = [
        int(r[0])
        for r in db.query(ClassroomAssessment.assessment_id)
        .filter(ClassroomAssessment.classroom_id == int(classroom_id))
        .all()
    ]

    attempts: List[Attempt] = []
    if assessment_ids and student_ids:
        attempts = (
            db.query(Attempt)
            .filter(Attempt.quiz_set_id.in_(assessment_ids), Attempt.user_id.in_(student_ids))
            .order_by(Attempt.created_at.asc())
            .all()
        )
    quiz_kind_map = {
        int(qid): str(kind or "")
        for qid, kind in db.query(QuizSet.id, QuizSet.kind).filter(QuizSet.id.in_(assessment_ids)).all()
    } if assessment_ids else {}

    per_student: Dict[int, Dict[str, Any]] = {uid: {"entry": None, "final": None} for uid in student_ids}
    for at in attempts:
        uid = int(at.user_id)
        kind = quiz_kind_map.get(int(at.quiz_set_id), "")
        if kind == "diagnostic_pre":
            per_student[uid]["entry"] = at
        elif kind == "diagnostic_post":
            per_student[uid]["final"] = at

    all_dates = [a.created_at for a in attempts if getattr(a, "created_at", None)]
    period = {
        "from": min(all_dates).isoformat() if all_dates else None,
        "to": max(all_dates).isoformat() if all_dates else None,
    }

    entry_scores: List[float] = []
    final_scores: List[float] = []
    improved = 0
    completed_both = 0
    level_dist = {"gioi": 0, "kha": 0, "trung_binh": 0, "yeu": 0}
    students: List[Dict[str, Any]] = []
    topic_agg: Dict[str, Dict[str, float]] = {}

    for uid in student_ids:
        entry_attempt = per_student.get(uid, {}).get("entry")
        final_attempt = per_student.get(uid, {}).get("final")
        entry_score = float(getattr(entry_attempt, "score_percent", 0.0) or 0.0)
        final_score = float(getattr(final_attempt, "score_percent", 0.0) or 0.0)
        if entry_attempt:
            entry_scores.append(entry_score)
        if final_attempt:
            final_scores.append(final_score)

        if entry_attempt and final_attempt:
            completed_both += 1
            if final_score > entry_score:
                improved += 1

        level = classify_student_level(int(round(final_score)))
        level_key = str(level["level_key"])
        level_dist[level_key] = int(level_dist.get(level_key, 0) or 0) + 1

        final_breakdown = score_breakdown(getattr(final_attempt, "breakdown_json", []) or []) if final_attempt else {}
        weak_topics = [
            str(t)
            for t, info in sorted(
                (final_breakdown.get("by_topic") or {}).items(), key=lambda x: float((x[1] or {}).get("percent") or 0.0)
            )[:3]
        ]

        entry_topics = score_breakdown(getattr(entry_attempt, "breakdown_json", []) or []).get("by_topic", {}) if entry_attempt else {}
        final_topics = (final_breakdown.get("by_topic") or {}) if final_breakdown else {}
        for topic in set(list(entry_topics.keys()) + list(final_topics.keys())):
            bucket = topic_agg.setdefault(str(topic), {"entry_sum": 0.0, "entry_n": 0.0, "final_sum": 0.0, "final_n": 0.0, "mastery_n": 0.0})
            ep = float((entry_topics.get(topic) or {}).get("percent") or 0.0)
            fp = float((final_topics.get(topic) or {}).get("percent") or 0.0)
            if topic in entry_topics:
                bucket["entry_sum"] += ep
                bucket["entry_n"] += 1
            if topic in final_topics:
                bucket["final_sum"] += fp
                bucket["final_n"] += 1
                if fp >= 70.0:
                    bucket["mastery_n"] += 1

        students.append(
            {
                "user_id": int(uid),
                "name": str(getattr(db.query(User).filter(User.id == int(uid)).first(), "full_name", "") or f"User #{uid}"),
                "level": level_key,
                "entry_score": round(entry_score, 2),
                "final_score": round(final_score, 2),
                "improvement": round(final_score - entry_score, 2),
                "weak_topics": weak_topics,
                "ai_assessment": generate_student_ai_assessment(db, uid, entry_attempt, final_attempt),
            }
        )

    topic_analysis = []
    for topic, vals in topic_agg.items():
        entry_avg = float(vals["entry_sum"]) / max(1.0, float(vals["entry_n"]))
        final_avg = float(vals["final_sum"]) / max(1.0, float(vals["final_n"]))
        mastery_rate = (float(vals["mastery_n"]) / max(1.0, float(vals["final_n"]))) * 100.0
        topic_analysis.append(
            {
                "topic": str(topic),
                "avg_score_entry": round(entry_avg, 2),
                "avg_score_final": round(final_avg, 2),
                "mastery_rate": round(mastery_rate, 2),
            }
        )
    topic_analysis.sort(key=lambda x: float(x.get("mastery_rate") or 0.0))

    avg_entry = sum(entry_scores) / max(1, len(entry_scores))
    avg_final = sum(final_scores) / max(1, len(final_scores))
    improvement_rate = (improved / max(1, completed_both)) * 100.0

    bloom_stub = [
        {"student_id": s["user_id"], "bloom_accuracy": {"remember": s["final_score"]}}
        for s in students
    ]
    class_narrative = generate_class_narrative(
        total_students=len(student_ids),
        level_dist=level_dist,
        weak_topics=[{"topic": t["topic"]} for t in topic_analysis[:3]],
        avg_improvement=avg_final - avg_entry,
        per_student_data=bloom_stub,
    )

    return {
        "report_title": f"Báo cáo tổng kết lớp học - {class_name}",
        "period": period,
        "class_stats": {
            "total_students": len(student_ids),
            "completed_both_tests": completed_both,
            "avg_entry_score": round(avg_entry, 2),
            "avg_final_score": round(avg_final, 2),
            "improvement_rate": round(improvement_rate, 2),
            "distribution": level_dist,
        },
        "topic_analysis": topic_analysis,
        "students": students,
        "ai_class_narrative": class_narrative,
    }


def export_classroom_final_report_pdf(report: Dict[str, Any], classroom_id: int) -> str:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    font_name = "Helvetica"
    noto_path = get_noto_sans_font_path()
    if noto_path and os.path.exists(noto_path):
        try:
            font_name = "NotoSans"
            pdfmetrics.registerFont(TTFont(font_name, noto_path))
        except Exception:
            font_name = "Helvetica"

    fd, output_path = tempfile.mkstemp(prefix=f"final_report_{int(classroom_id)}_", suffix=".pdf")
    os.close(fd)
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    y = height - 40

    def _line(text: str, size: int = 11, step: int = 15) -> None:
        nonlocal y
        if y < 40:
            c.showPage()
            y = height - 40
        c.setFont(font_name, size)
        c.drawString(40, y, text)
        y -= step

    _line(str(report.get("report_title") or f"Báo cáo lớp {int(classroom_id)}"), 14, 20)
    period = report.get("period") or {}
    _line(f"Giai đoạn: {period.get('from') or 'N/A'} -> {period.get('to') or 'N/A'}")
    stats = report.get("class_stats") or {}
    _line(
        f"Sĩ số: {int(stats.get('total_students') or 0)} | Hoàn thành đủ 2 bài: {int(stats.get('completed_both_tests') or 0)}"
    )
    _line(
        f"Điểm TB Entry: {float(stats.get('avg_entry_score') or 0):.1f} | Điểm TB Final: {float(stats.get('avg_final_score') or 0):.1f}"
    )
    _line(f"Tỷ lệ cải thiện: {float(stats.get('improvement_rate') or 0):.1f}%")
    _line("Nhận xét tổng quát:", 12, 16)
    for paragraph in str(report.get("ai_class_narrative") or "").split(". "):
        text = paragraph.strip()
        if text:
            _line(f"- {text}")

    _line("Top chủ đề cần ưu tiên:", 12, 16)
    for topic in (report.get("topic_analysis") or [])[:5]:
        _line(
            f"• {topic.get('topic')}: mastery {float(topic.get('mastery_rate') or 0):.1f}% | entry {float(topic.get('avg_score_entry') or 0):.1f} | final {float(topic.get('avg_score_final') or 0):.1f}"
        )

    _line("Danh sách học sinh:", 12, 16)
    for st in report.get("students") or []:
        _line(
            f"- {st.get('name')} ({st.get('level')}): {float(st.get('entry_score') or 0):.1f} -> {float(st.get('final_score') or 0):.1f} ({float(st.get('improvement') or 0):+.1f})"
        )

    c.save()
    return str(Path(output_path))


def render_teacher_final_report_html(report: Dict[str, Any]) -> str:
    template_path = Path(__file__).resolve().parent.parent / "resources" / "final_report_teacher_template.html"
    template = template_path.read_text(encoding="utf-8")

    topic_rows = "".join(
        f"<tr><td>{t.get('topic')}</td><td>{t.get('avg_score_entry')}</td><td>{t.get('avg_score_final')}</td><td>{t.get('mastery_rate')}%</td></tr>"
        for t in (report.get("topic_analysis") or [])
    )
    if topic_rows:
        topic_rows = "<table><tr><th>Chủ đề</th><th>Entry</th><th>Final</th><th>Mastery</th></tr>" + topic_rows + "</table>"

    student_rows = "".join(
        f"<tr><td>{s.get('name')}</td><td>{s.get('level')}</td><td>{s.get('entry_score')}</td><td>{s.get('final_score')}</td><td>{s.get('improvement')}</td></tr>"
        for s in (report.get("students") or [])
    )
    if student_rows:
        student_rows = "<table><tr><th>Học sinh</th><th>Mức</th><th>Entry</th><th>Final</th><th>Tiến bộ</th></tr>" + student_rows + "</table>"

    period = report.get("period") or {}
    stats = report.get("class_stats") or {}
    html = template
    replacements = {
        "{{ report_title }}": str(report.get("report_title") or "Báo cáo lớp học"),
        "{{ period_from }}": str(period.get("from") or "N/A"),
        "{{ period_to }}": str(period.get("to") or "N/A"),
        "{{ total_students }}": str(stats.get("total_students") or 0),
        "{{ completed_both_tests }}": str(stats.get("completed_both_tests") or 0),
        "{{ avg_entry_score }}": str(stats.get("avg_entry_score") or 0),
        "{{ avg_final_score }}": str(stats.get("avg_final_score") or 0),
        "{{ improvement_rate }}": str(stats.get("improvement_rate") or 0),
        "{{ topic_rows_html }}": topic_rows or "<p>Chưa có dữ liệu chủ đề.</p>",
        "{{ student_rows_html }}": student_rows or "<p>Chưa có dữ liệu học sinh.</p>",
        "{{ ai_class_narrative }}": str(report.get("ai_class_narrative") or ""),
    }
    for k, v in replacements.items():
        html = html.replace(k, v)
    return html
