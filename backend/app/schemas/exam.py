from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


Level = Literal["beginner", "intermediate", "advanced"]
AssessmentKind = Literal["diagnostic_pre", "midterm", "diagnostic_post"]
ExportFormat = Literal["pdf", "docx"]
ReportExportFormat = Literal["pdf", "xlsx"]


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
    classroom_id: int = 1
    title: Optional[str] = None
    level: Level = "beginner"
    document_ids: List[int] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)


class ExamGenerateVariantsRequest(BaseModel):
    teacher_id: int = 1
    classroom_id: int = 1
    title_prefix: str = "Variant"
    level: Level = "intermediate"
    kind: AssessmentKind = "midterm"
    template_id: Optional[str] = None
    n_variants: int = Field(default=2, ge=1, le=20)
    easy_count: int = Field(default=5, ge=0, le=50)
    medium_count: int = Field(default=5, ge=0, le=50)
    hard_count: int = Field(default=2, ge=0, le=20)
    document_ids: List[int] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    exclude_assessment_ids: List[int] = Field(default_factory=list)
    similarity_threshold: float = Field(default=0.72, ge=0.3, le=0.95)


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


class BatchExamGenerateRequest(BaseModel):
    teacher_id: Optional[int] = None
    classroom_id: int
    title: str
    document_ids: List[int] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    num_papers: int = Field(ge=1, le=10, default=3)
    questions_per_paper: int = Field(ge=5, le=100, default=20)
    mcq_ratio: float = Field(ge=0.0, le=1.0, default=0.7)
    difficulty_distribution: Dict[str, float] = Field(
        default_factory=lambda: {"easy": 0.3, "medium": 0.4, "hard": 0.3}
    )
    similarity_threshold: float = 0.75
    include_answer_key: bool = True
    paper_code_style: Literal["ABC", "NUM"] = "ABC"
