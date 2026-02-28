from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Level = Literal["beginner", "intermediate", "advanced"]
AssessmentKind = Literal["diagnostic_pre", "midterm", "diagnostic_post"]


class AssessmentGenerateRequest(BaseModel):
    # classroom_id is required to keep assessments separated per class
    classroom_id: int

    title: str = "Assessment"
    level: Level = "beginner"
    kind: AssessmentKind = "midterm"

    # Easy = MCQ; Hard = essay
    easy_count: int = Field(default=5, ge=1, le=50)
    hard_count: int = Field(default=2, ge=0, le=20)

    document_ids: List[int] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)


class AssessmentQuestionOut(BaseModel):
    question_id: int
    type: Literal["mcq", "essay"]
    stem: str
    options: List[str] = Field(default_factory=list)

    # For essay
    max_points: int = 0
    rubric: List[Dict[str, Any]] = Field(default_factory=list)

    sources: List[Dict[str, Any]] = Field(default_factory=list)

    # AI-estimated time (minutes) for this question.
    estimated_minutes: int = 0


class AssessmentOut(BaseModel):
    assessment_id: int
    title: str
    level: Level
    # Total time limit (minutes), typically the sum of per-question estimated_minutes.
    time_limit_minutes: int = 0
    questions: List[AssessmentQuestionOut]


class AssessmentAnswer(BaseModel):
    question_id: int
    answer_index: Optional[int] = None
    answer_text: Optional[str] = None


class AssessmentSubmitRequest(BaseModel):
    user_id: int
    # Deprecated: duration is now enforced server-side.
    duration_sec: int = 0
    answers: List[AssessmentAnswer]


class AssessmentSubmitOut(BaseModel):
    assessment_id: int
    attempt_id: int
    score_percent: int
    score_points: int
    max_points: int
    status: str
    breakdown: List[Dict[str, Any]]


class TeacherAssessmentListItem(BaseModel):
    assessment_id: int
    classroom_id: int
    title: str
    level: str
    kind: str
    created_at: str


class TeacherLeaderboardRow(BaseModel):
    user_id: int
    attempt_id: int
    score_percent: int
    created_at: str


class TeacherLeaderboardOut(BaseModel):
    assessment_id: int
    title: str
    leaderboard: List[TeacherLeaderboardRow]


class EssayGradeItem(BaseModel):
    question_id: int
    score_points: int = Field(ge=0)
    comment: Optional[str] = None


class TeacherGradeRequest(BaseModel):
    student_id: int
    grades: List[EssayGradeItem]
