from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


Level = Literal["beginner", "intermediate", "advanced"]
AssessmentKind = Literal["diagnostic_pre", "midterm", "diagnostic_post"]
ExportFormat = Literal["pdf", "docx"]


class ExamTemplateSection(BaseModel):
    """A high-level section definition (template input)."""

    type: Literal["multiple_choice", "essay"]
    count: int = Field(ge=0, le=100)
    points_per_question: int = Field(default=1, ge=1, le=100)
    difficulty: Optional[Literal["easy", "medium", "hard"]] = None


class ExamTemplateMetadata(BaseModel):
    grade_level: int = Field(default=10, ge=1, le=12)
    subject: str = ""
    duration_minutes: int = Field(default=45, ge=5, le=240)
    total_points: int = Field(default=100, ge=1, le=500)


class ExamTemplateOut(BaseModel):
    template_id: str
    name: str
    kind: AssessmentKind
    metadata: ExamTemplateMetadata
    sections: List[ExamTemplateSection]


class ExamGenerateFromTemplateRequest(BaseModel):
    template_id: str
    teacher_id: int = 1
    title: Optional[str] = None
    level: Level = "beginner"
    document_ids: List[int] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)


class ExamAnalyzeOut(BaseModel):
    assessment_id: int
    title: str
    level: str
    kind: str
    question_count: int
    by_type: Dict[str, int]
    by_bloom: Dict[str, int]
    by_topic: Dict[str, int]
    estimated_points: int
    notes: List[str] = Field(default_factory=list)
