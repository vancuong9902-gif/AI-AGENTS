from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AnalyticsWeightsIn(BaseModel):
    user_id: int
    w1_knowledge: float = Field(0.45, ge=0.0)
    w2_improvement: float = Field(0.25, ge=0.0)
    w3_engagement: float = Field(0.15, ge=0.0)
    w4_retention: float = Field(0.15, ge=0.0)


class DropoutPrediction(BaseModel):
    risk: float
    band: str
    drivers: List[Dict[str, Any]]


class CompositeAnalytics(BaseModel):
    scope: str
    weights: Dict[str, float]
    knowledge: float
    improvement: float
    engagement: float
    retention: float
    final_score: float
    dropout: DropoutPrediction
    updated_at: str


class TopicDashboardRow(BaseModel):
    topic_id: int
    topic_index: int
    title: str
    mastery: float
    last_score_percent: Optional[int] = None
    next_step: Optional[str] = None
    next_difficulty: Optional[str] = None
    retention_due_count: int = 0
    retention_completed_count_60d: int = 0
    half_life_days: Optional[float] = None


class DashboardResponse(BaseModel):
    user_id: int
    document_id: Optional[int] = None
    window_days: int
    analytics: CompositeAnalytics
    topics: List[TopicDashboardRow]
    activity: Dict[str, Any]
