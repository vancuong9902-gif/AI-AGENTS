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
    rubric_breakdown: List[Dict[str, Any]] = Field(default_factory=list)
