from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, Field

Level = Literal["beginner", "intermediate", "advanced"]

class QuestionBankGenerateRequest(BaseModel):
    user_id: int = Field(..., description="Teacher user id (demo headers may also be used)")
    levels: List[Level] = Field(default_factory=lambda: ["beginner", "intermediate", "advanced"])
    question_count_per_level: int = Field(10, ge=1, le=50)
    # Optional: only generate for selected topic ids
    topic_ids: Optional[List[int]] = None
    # RAG
    rag_top_k: int = Field(6, ge=1, le=30)

class QuestionBankGenerateData(BaseModel):
    document_id: int
    topic_count: int
    levels: List[Level]
    question_count_per_level: int
    results: list[dict] = Field(default_factory=list)
