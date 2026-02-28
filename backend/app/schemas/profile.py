from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


Level = Literal["beginner", "intermediate", "advanced"]
AssessmentStage = Literal["pre", "post"]


class DiagnosticQuestionOut(BaseModel):
    question_id: int
    question: str
    options: List[str]
    # Optional grouping label (helps build learning-path modules by topic group)
    topic: Optional[str] = None


class DiagnosticAnswerIn(BaseModel):
    question_id: int
    answer: int = Field(..., ge=0, le=3)


class DiagnosticRequest(BaseModel):
    user_id: int = 1
    answers: List[DiagnosticAnswerIn]


class DiagnosticResultData(BaseModel):
    attempt_id: int
    stage: AssessmentStage
    user_id: int
    score_percent: int
    correct_count: int
    total: int
    level: Level
    # Chủ đề giáo viên giao ở bài test đầu vào (nếu có)
    assigned_topic: Optional[str] = None
    assigned_mastery: Optional[float] = None


class FinalResultData(BaseModel):
    attempt_id: int
    stage: AssessmentStage = "post"
    user_id: int
    score_percent: int
    correct_count: int
    total: int
    level: Level
    # Chủ đề giáo viên giao ở bài test đầu vào (nếu có)
    assigned_topic: Optional[str] = None
    assigned_mastery: Optional[float] = None
    pre_score_percent: Optional[int] = None
    delta_score: Optional[int] = None


class LearnerProfileData(BaseModel):
    user_id: int
    level: Level
    # Chủ đề giáo viên giao ở bài test đầu vào (nếu có)
    assigned_topic: Optional[str] = None
    assigned_mastery: Optional[float] = None
    mastery: Dict[str, float] = Field(default_factory=dict)


class NextRecommendationData(BaseModel):
    topic: str
    recommended_level: Level
    mastery: float
    reason: str
    extra: Dict[str, Any] = Field(default_factory=dict)


class LearningMaterial(BaseModel):
    chunk_id: int
    document_id: int | None = None
    document_title: str | None = None
    preview: str | None = None


class LearningModule(BaseModel):
    topic: str
    recommended_level: Level
    mastery: float
    goal: str
    # Optional mini-lesson generated from materials (markdown-ish text for UI)
    lesson_md: Optional[str] = None
    materials: List[LearningMaterial] = Field(default_factory=list)
    quiz_recommendation: Dict[str, Any] = Field(default_factory=dict)
    # Hidden evidence pointers used to build teacher-style homework and grading.
    # Frontend does not have to show these.
    evidence_chunk_ids: List[int] = Field(default_factory=list)


class LearningPlanTask(BaseModel):
    type: Literal["read", "note", "practice", "quiz", "review", "homework", "checkpoint"]
    title: str
    instructions: str
    estimated_minutes: int = 0
    payload: Dict[str, Any] = Field(default_factory=dict)


class HomeworkMCQQuestion(BaseModel):
    """A small MCQ item bundled into the daily homework.

    We keep it simple (4 options) and store grounding pointers (chunk_id).
    """

    question_id: str
    stem: str
    options: List[str] = Field(default_factory=list)
    correct_index: int = Field(..., ge=0)
    explanation: Optional[str] = None
    max_points: int = 1
    sources: List[Dict[str, int]] = Field(default_factory=list)


class HomeworkPrompt(BaseModel):
    stem: str
    max_points: int = 10
    rubric: List[Dict[str, Any]] = Field(default_factory=list)
    sources: List[Dict[str, int]] = Field(default_factory=list)
    # Optional: mixed homework (MCQ + essay). Essay uses the fields above.
    mcq_questions: List[HomeworkMCQQuestion] = Field(default_factory=list)


class LearningPlanDay(BaseModel):
    day_index: int
    title: str
    objectives: List[str] = Field(default_factory=list)
    recommended_minutes: int = 35
    # "Textbook" lesson for the day (student reads 1 lesson/day).
    lesson_md: Optional[str] = None
    tasks: List[LearningPlanTask] = Field(default_factory=list)
    homework: Optional[HomeworkPrompt] = None


class TeacherLearningPlan(BaseModel):
    plan_id: Optional[int] = None
    days: List[LearningPlanDay] = Field(default_factory=list)
    summary: Optional[str] = None
    days_total: int = 7
    minutes_per_day: int = 35


class LearningPathData(BaseModel):
    user_id: int
    level: Level
    # Chủ đề giáo viên giao ở bài test đầu vào (nếu có)
    assigned_topic: Optional[str] = None
    assigned_mastery: Optional[float] = None
    # Mastery summary from the pre-test (can include both weak and non-weak topics)
    topic_mastery: Dict[str, float] = Field(default_factory=dict)
    weak_topics: List[str] = Field(default_factory=list)
    modules: List[LearningModule] = Field(default_factory=list)
    # Teacher-style daily plan (optional)
    teacher_plan: Optional[TeacherLearningPlan] = None
    # Optional note for UI (e.g., "please run diagnostic" or "no weak topics")
    note: Optional[str] = None
