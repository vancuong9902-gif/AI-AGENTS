from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class HomeworkGradeRequest(BaseModel):
    user_id: int = 1
    stem: str
    answer_text: str
    max_points: int = 10
    rubric: List[Dict[str, Any]] = Field(default_factory=list)
    sources: List[Dict[str, int]] = Field(default_factory=list)


class HomeworkGradeResult(BaseModel):
    score_points: int
    max_points: int
    comment: str
    explanation: Optional[str] = None
    hint: Optional[str] = None
    rubric_breakdown: List[Dict[str, Any]] = Field(default_factory=list)


class HomeworkMCQQuestion(BaseModel):
    question_id: str
    stem: str
    options: List[str] = Field(default_factory=list)
    correct_index: int = Field(..., ge=0)
    explanation: Optional[str] = None
    hint: Optional[str] = None
    related_concept: Optional[str] = None
    max_points: int = 1
    sources: List[Dict[str, int]] = Field(default_factory=list)
