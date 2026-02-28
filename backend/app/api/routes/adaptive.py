from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.adaptive import (
    AdaptiveFeedbackOut,
    AdaptiveFeedbackRequest,
    AdaptiveNextActionOut,
    AdaptiveNextActionRequest,
)
from app.services.adaptive_policy_service import apply_feedback, recommend_next_action
from app.models.policy_decision_log import PolicyDecisionLog


router = APIRouter(tags=["adaptive"])


@router.post("/adaptive/next-action", response_model=AdaptiveNextActionOut)
def adaptive_next_action(request: Request, payload: AdaptiveNextActionRequest, db: Session = Depends(get_db)):
    data = recommend_next_action(
        db,
        user_id=int(payload.user_id),
        document_id=(int(payload.document_id) if payload.document_id is not None else None),
        topic=(payload.topic or None),
        last_attempt_id=(int(payload.last_attempt_id) if payload.last_attempt_id is not None else None),
        recent_accuracy=(float(payload.recent_accuracy) if payload.recent_accuracy is not None else None),
        avg_time_per_item_sec=(float(payload.avg_time_per_item_sec) if payload.avg_time_per_item_sec is not None else None),
        engagement=(float(payload.engagement) if payload.engagement is not None else None),
        current_difficulty=(payload.current_difficulty or None),
        policy_type=str(payload.policy_type),
        epsilon=float(payload.epsilon),
    )
    try:
        row = PolicyDecisionLog(
            user_id=int(payload.user_id),
            document_id=(int(payload.document_id) if payload.document_id is not None else None),
            topic=(payload.topic or None),
            policy_type=str(payload.policy_type),
            action=str((data or {}).get('action') or ''),
            recommended_difficulty=str((data or {}).get('recommended_difficulty') or (data or {}).get('difficulty') or ''),
            state_json=(data or {}).get('state') or {},
            meta_json={'source': 'adaptive_next_action'},
        )
        db.add(row)
        db.commit()
    except Exception:
        db.rollback()
        pass

    return jsonable_encoder(data)


@router.post("/adaptive/feedback", response_model=AdaptiveFeedbackOut)
def adaptive_feedback(request: Request, payload: AdaptiveFeedbackRequest, db: Session = Depends(get_db)):
    state = payload.state or {}
    if not state:
        # Minimal placeholder state prevents crashes; callers should pass a real state.
        state = {
            "bins": {"acc": 1, "time": 1, "eng": 1, "mastery": 1, "difficulty": 0},
            "acc": 0.7,
            "mastery": 0.5,
            "engagement": 0.6,
            "avg_time_per_item_sec": 45.0,
            "topic": payload.topic or "__global__",
        }

    data = apply_feedback(
        db,
        user_id=int(payload.user_id),
        policy_type=str(payload.policy_type),
        state=state,
        action=str(payload.action),
        reward=(float(payload.reward) if payload.reward is not None else None),
        attempt_id=(int(payload.attempt_id) if payload.attempt_id is not None else None),
        next_state=(payload.next_state or None),
        alpha=float(payload.alpha),
        gamma=float(payload.gamma),
    )
    return jsonable_encoder(data)
