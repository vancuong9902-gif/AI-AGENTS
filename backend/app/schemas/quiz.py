from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

Level = Literal["beginner", "intermediate", "advanced"]


class QuizRAG(BaseModel):
    query: str
    top_k: int = 6
    filters: Dict[str, Any] = Field(default_factory=dict)


class QuizGenerateRequest(BaseModel):
    user_id: int
    topic: str
    level: Level
    question_count: int = 5
    rag: QuizRAG


class QuizQuestionOut(BaseModel):
    question_id: int
    type: str = "mcq"
    bloom_level: Optional[str] = None
    stem: str
    options: List[str]


class QuizGenerateData(BaseModel):
    quiz_id: int
    topic: str
    level: Level
    questions: List[QuizQuestionOut]
    sources: List[Dict[str, Any]] = Field(default_factory=list)


class SubmitAnswer(BaseModel):
    question_id: int
    answer: int


class QuizSubmitRequest(BaseModel):
    user_id: int
    duration_sec: int = 0
    answers: List[SubmitAnswer]


class BreakdownItem(BaseModel):
    question_id: int
    bloom_level: Optional[str] = None
    is_correct: bool
    chosen: int
    correct: int
    explanation: Optional[str] = None
    sources: List[Dict[str, Any]] = Field(default_factory=list)


class QuizSubmitData(BaseModel):
    quiz_id: int
    attempt_id: int
    score_percent: int
    correct_count: int
    total: int
    breakdown: List[BreakdownItem]
    mastery_updated: Optional[Dict[str, Any]] = None
