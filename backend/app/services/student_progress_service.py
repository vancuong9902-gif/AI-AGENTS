from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

from sqlalchemy.orm import Session

from app.models.attempt import Attempt


def compute_learning_curve(student_id: int, db: Session) -> list[dict[str, Any]]:
    """Lấy trajectory điểm theo thời gian cho học sinh."""
    attempts = (
        db.query(Attempt)
        .filter(Attempt.user_id == int(student_id))
        .order_by(Attempt.created_at.asc())
        .all()
    )
    curve: list[dict[str, Any]] = []
    for idx, at in enumerate(attempts, start=1):
        score = float(getattr(at, "score_percent", 0) or 0)
        curve.append(
            {
                "attempt_id": int(at.id),
                "index": idx,
                "score": round(score, 2),
                "created_at": at.created_at.isoformat() if getattr(at, "created_at", None) else None,
            }
        )
    return curve


def detect_knowledge_gaps(student_id: int, db: Session) -> list[dict[str, Any]]:
    """Phát hiện topic học sinh liên tục làm sai (<50%)."""
    attempts = (
        db.query(Attempt)
        .filter(Attempt.user_id == int(student_id))
        .order_by(Attempt.created_at.asc())
        .all()
    )
    topic_scores: dict[str, list[float]] = defaultdict(list)
    for at in attempts:
        for item in (at.breakdown_json or []):
            topic = str((item or {}).get("topic") or "tong_hop").strip().lower()
            max_points = float((item or {}).get("max_points") or 1.0)
            earned = float((item or {}).get("score_points") or 0.0)
            pct = (earned / max_points) * 100 if max_points > 0 else 0.0
            topic_scores[topic].append(round(pct, 2))

    gaps: list[dict[str, Any]] = []
    for topic, series in topic_scores.items():
        if len(series) < 2:
            continue
        tail = series[-3:]
        avg_tail = mean(tail)
        consecutive_weak = all(x < 50 for x in tail)
        if consecutive_weak or avg_tail < 45:
            gaps.append(
                {
                    "topic": topic,
                    "recent_scores": tail,
                    "avg_recent": round(avg_tail, 1),
                    "severity": "high" if avg_tail < 35 else "medium",
                }
            )

    return sorted(gaps, key=lambda x: x["avg_recent"])


def predict_final_score(student_id: int, db: Session) -> dict[str, Any]:
    """Dự báo điểm cuối kỳ đơn giản dựa trên trend tuyến tính theo attempts."""
    curve = compute_learning_curve(student_id, db)
    if not curve:
        return {"student_id": int(student_id), "predicted_final_score": 0.0, "confidence": "low"}

    scores = [float(c["score"]) for c in curve]
    if len(scores) == 1:
        pred = scores[0]
    else:
        step_gains = [scores[i] - scores[i - 1] for i in range(1, len(scores))]
        pred = scores[-1] + mean(step_gains)

    pred = max(0.0, min(100.0, pred))
    confidence = "high" if len(scores) >= 6 else "medium" if len(scores) >= 3 else "low"
    return {
        "student_id": int(student_id),
        "predicted_final_score": round(pred, 1),
        "confidence": confidence,
        "based_on_attempts": len(scores),
    }
