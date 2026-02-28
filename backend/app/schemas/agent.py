from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ==========================================================
# Teaching Agent schemas (Phase-based adaptive learning)
# ==========================================================

Level = Literal["beginner", "intermediate", "advanced"]


class AgentTopicPackage(BaseModel):
    topic_id: int
    topic_index: int
    title: str

    # Phase 1 fields
    learning_objectives: List[str] = Field(default_factory=list)
    core_concepts: List[str] = Field(default_factory=list)
    key_definitions: List[Dict[str, str]] = Field(default_factory=list)  # {term, definition}
    important_formulas: List[str] = Field(default_factory=list)
    worked_examples: List[str] = Field(default_factory=list)
    common_mistakes: List[str] = Field(default_factory=list)
    practical_applications: List[str] = Field(default_factory=list)

    # Optional enrichments / UI helpers
    summary: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    outline: List[str] = Field(default_factory=list)
    study_guide_md: Optional[str] = None
    self_check: List[str] = Field(default_factory=list)
    content_preview: Optional[str] = None


class AgentPhase1Out(BaseModel):
    document_id: int
    title: str
    doc_summary: str = ""
    topics: List[AgentTopicPackage]


class EntryTestGenerateRequest(BaseModel):
    user_id: int = 2
    document_ids: List[int] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    language: str = "vi"
    # If provided, overrides doc/topic selection for retrieval.
    rag_query: Optional[str] = None


class AgentQuestionOut(BaseModel):
    question_id: int
    order_no: int
    section: Literal["EASY", "MEDIUM", "HARD"]
    qtype: Literal["mcq", "short_answer", "application", "analytical", "complex"]
    stem: str
    options: List[str] = Field(default_factory=list)


class EntryTestGenerateOut(BaseModel):
    quiz_id: int
    kind: str
    title: str
    questions: List[AgentQuestionOut]


class AgentSubmitAnswer(BaseModel):
    question_id: int
    answer_index: Optional[int] = None
    answer_text: Optional[str] = None


class EntryTestSubmitRequest(BaseModel):
    user_id: int
    duration_sec: int = 0
    answers: List[AgentSubmitAnswer]


class AgentQuestionBreakdown(BaseModel):
    question_id: int
    section: str
    qtype: str
    is_correct: bool
    score_points: float
    max_points: float
    chosen: Optional[int] = None
    student_answer: Optional[str] = None
    correct_index: Optional[int] = None
    ideal_answer: Optional[str] = None
    explanation: Optional[str] = None
    feedback: Optional[str] = None
    sources: List[Dict[str, Any]] = Field(default_factory=list)


class EntryTestSubmitOut(BaseModel):
    quiz_id: int
    attempt_id: int
    score_percent: int
    score_points: float
    max_points: float
    classification: Level
    breakdown: List[AgentQuestionBreakdown]
    improvement_suggestions: List[str] = Field(default_factory=list)


class FinalExamGenerateRequest(BaseModel):
    user_id: int = 2
    document_ids: List[int] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    language: str = "vi"
    rag_query: Optional[str] = None


class FinalExamGenerateOut(BaseModel):
    quiz_id: int
    kind: str
    title: str
    questions: List[AgentQuestionOut]


class FinalExamSubmitRequest(EntryTestSubmitRequest):
    pass


class FinalExamSubmitOut(EntryTestSubmitOut):
    analytics: Dict[str, Any] = Field(default_factory=dict)


# ------------------------------
# Phase 4: Topic Mastery Loop
# ------------------------------


Difficulty = Literal["easy", "medium", "hard"]


class TopicExercisesGenerateRequest(BaseModel):
    user_id: int
    topic_id: int
    language: str = "vi"
    difficulty: Optional[Difficulty] = None


class TopicExercisesGenerateOut(BaseModel):
    quiz_id: int
    kind: str
    topic_id: int
    document_id: int
    topic_title: str
    topic_key: str
    learner_level: Level
    difficulty: Difficulty
    recap_md: Optional[str] = None
    questions: List[AgentQuestionOut]


class TopicExercisesSubmitRequest(EntryTestSubmitRequest):
    topic_id: int


class TopicExercisesSubmitOut(EntryTestSubmitOut):
    topic_id: int
    document_id: int
    topic_title: str
    topic_key: str
    topic_score_percent: int
    mastery_estimate: float
    next_step: Literal["increase_difficulty", "reinforce", "continue"]
    next_difficulty: Difficulty
