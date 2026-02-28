from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TutorChatRequest(BaseModel):
    user_id: int
    question: str
    topic: Optional[str] = None

    # retrieval controls
    top_k: int = 6
    document_ids: Optional[List[int]] = None


class TutorSource(BaseModel):
    chunk_id: int
    document_id: Optional[int] = None
    document_title: Optional[str] = None
    score: float = 0.0
    preview: str = ""
    meta: Dict[str, Any] = Field(default_factory=dict)


class TutorChatData(BaseModel):
    answer_md: str
    was_answered: bool = True
    off_topic_reason: Optional[str] = None
    suggested_topics: List[str] = Field(default_factory=list)
    follow_up_questions: List[str] = Field(default_factory=list)
    quick_check_mcq: List[Dict[str, Any]] = Field(default_factory=list)
    sources: List[TutorSource] = Field(default_factory=list)
    retrieval: Dict[str, Any] = Field(default_factory=dict)


# -----------------------------
# Practice mode: AI generates questions from the teacher's documents
# -----------------------------


class TutorGenerateQuestionsRequest(BaseModel):
    user_id: int
    topic: str
    level: Optional[str] = None

    question_count: int = 6

    # retrieval controls
    top_k: int = 8
    document_ids: Optional[List[int]] = None


class TutorPracticeQuestion(BaseModel):
    type: str = "open_ended"
    stem: str
    hints: List[str] = Field(default_factory=list)
    sources: List[Dict[str, int]] = Field(default_factory=list)


class TutorGenerateQuestionsData(BaseModel):
    topic: str
    level: Optional[str] = None
    questions: List[TutorPracticeQuestion] = Field(default_factory=list)
    sources: List[TutorSource] = Field(default_factory=list)
    retrieval: Dict[str, Any] = Field(default_factory=dict)
