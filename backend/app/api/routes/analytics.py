from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.analytics import AnalyticsWeightsIn
from app.services.analytics_service import (
    compute_composite_analytics,
    dashboard_topics,
    get_analytics_history,
    set_analytics_weights,
    update_profile_analytics,
)

router = APIRouter(tags=["analytics"])


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
