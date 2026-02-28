from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


Status = Literal["pending", "completed", "expired", "cancelled"]


class RetentionScheduleOut(BaseModel):
    id: int
    user_id: int
    topic_id: int
    interval_days: int
    due_at: datetime
    status: Status
    baseline_score_percent: int = 0
    source_attempt_id: Optional[int] = None
    retention_quiz_set_id: Optional[int] = None
    retention_attempt_id: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class RetentionDueListOut(BaseModel):
    user_id: int
    now_utc: str
    due: List[RetentionScheduleOut] = Field(default_factory=list)
    upcoming: List[RetentionScheduleOut] = Field(default_factory=list)


class RetentionScheduleCreateRequest(BaseModel):
    user_id: int
    topic_id: int
    baseline_score_percent: int = 0
    intervals_days: List[int] = Field(default_factory=lambda: [1, 7, 30])
    source_attempt_id: Optional[int] = None
    source_quiz_set_id: Optional[int] = None


class RetentionGenerateRequest(BaseModel):
    user_id: int
    language: str = "vi"
    difficulty: Optional[str] = None


class QuizAnswer(BaseModel):
    question_id: int
    answer_index: Optional[int] = None
    answer_text: Optional[str] = None


class RetentionSubmitRequest(BaseModel):
    user_id: int
    duration_sec: int = 0
    answers: List[QuizAnswer] = Field(default_factory=list)


class RetentionSubmitOut(BaseModel):
    schedule: RetentionScheduleOut
    graded: Dict[str, Any]
    retention_metrics: Dict[str, Any]
    delayed_reward: Dict[str, Any]
