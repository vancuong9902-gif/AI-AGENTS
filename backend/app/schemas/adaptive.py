from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


AdaptiveAction = Literal[
    "increase_difficulty",
    "decrease_difficulty",
    "switch_topic",
    "reinforce_weak_skill",
    "continue",
]

PolicyType = Literal["contextual_bandit", "q_learning"]


class AdaptiveNextActionRequest(BaseModel):
    """Request the next pedagogical action.

    Callers can provide either:
      - last_attempt_id (preferred), OR
      - minimal telemetry (recent_accuracy / avg_time_per_item_sec / engagement), OR
      - neither, in which case the service falls back to the learner profile priors.

    Note: The fields are intentionally model-agnostic to allow swapping policies.
    """

    user_id: int = Field(..., ge=1)
    document_id: Optional[int] = Field(default=None, ge=1)
    topic: Optional[str] = None

    # Optional telemetry
    last_attempt_id: Optional[int] = Field(default=None, ge=1)
    recent_accuracy: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    avg_time_per_item_sec: Optional[float] = Field(default=None, ge=0.0)
    engagement: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    current_difficulty: Optional[Literal["easy", "medium", "hard"]] = None
    policy_type: PolicyType = "contextual_bandit"
    epsilon: float = Field(default=0.08, ge=0.0, le=1.0)


class AdaptiveNextActionOut(BaseModel):
    user_id: int
    policy_type: PolicyType
    recommended_action: AdaptiveAction
    recommended_difficulty: Literal["easy", "medium", "hard"]
    rationale: str
    state: Dict[str, Any]
    policy_debug: Dict[str, Any] = {}


class AdaptiveFeedbackRequest(BaseModel):
    """Provide feedback for policy learning.

    reward is expected to be normalized (roughly [-1, +1]). If omitted and attempt_id
    is provided, the service derives a reward proxy from the attempt.
    """

    user_id: int = Field(..., ge=1)
    attempt_id: Optional[int] = Field(default=None, ge=1)
    topic: Optional[str] = None
    policy_type: PolicyType = "contextual_bandit"
    state: Optional[Dict[str, Any]] = None
    action: AdaptiveAction
    reward: Optional[float] = Field(default=None)
    next_state: Optional[Dict[str, Any]] = None
    gamma: float = Field(default=0.92, ge=0.0, le=1.0)
    alpha: float = Field(default=0.18, ge=0.0, le=1.0)


class AdaptiveFeedbackOut(BaseModel):
    user_id: int
    updated: bool
    policy_type: PolicyType
    debug: Dict[str, Any] = {}
