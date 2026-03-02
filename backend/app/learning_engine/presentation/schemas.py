from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentIngestRequest(BaseModel):
    document_id: str = Field(..., min_length=2)
    content: str = Field(..., min_length=20)


class EntranceTestRequest(BaseModel):
    student_id: str
    document_id: str


class LevelEvaluationRequest(BaseModel):
    student_id: str
    document_id: str
    entrance_score: float = Field(..., ge=0, le=1)


class ExerciseRequest(BaseModel):
    topic_id: str
    objective: str
    difficulty: str = "intermediate"


class ProgressUpdateRequest(BaseModel):
    student_id: str
    completion_rate: float = Field(..., ge=0, le=1)
    mastery_by_topic: dict[str, float]


class FinalReportRequest(BaseModel):
    student_id: str
    level: str
    completion_rate: float = Field(..., ge=0, le=1)
    mastery_by_topic: dict[str, float]
    exam_score: float = Field(..., ge=0, le=1)
