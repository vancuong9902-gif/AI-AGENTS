from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ClassroomCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ClassroomOut(BaseModel):
    id: int
    name: str
    join_code: str
    teacher_id: int
    student_count: int = 0


class ClassroomJoinRequest(BaseModel):
    join_code: str = Field(min_length=3, max_length=32)


class AssignLearningPlanRequest(BaseModel):
    assigned_topic: Optional[str] = None
    level: str = "beginner"
    days_total: int = 7
    minutes_per_day: int = 35


class StudentProgressRow(BaseModel):
    user_id: int
    full_name: Optional[str] = None
    tasks_done: int = 0
    tasks_total: int = 0
    homework_avg: Optional[float] = None
    last_homework_score: Optional[float] = None
    latest_plan_id: Optional[int] = None
    assigned_topic: Optional[str] = None


class ClassroomDashboardOut(BaseModel):
    classroom: ClassroomOut
    students: List[StudentProgressRow] = Field(default_factory=list)


class DifficultyDistributionIn(BaseModel):
    easy_pct: int = 30
    medium_pct: int = 40
    hard_pct: int = 30


class ClassroomEntryTestCreateRequest(BaseModel):
    teacher_id: int
    document_ids: List[int] = Field(default_factory=list)
    topic_ids: List[int] = Field(default_factory=list)
    title: str = "Entry Test"
    time_limit_minutes: int = 45
    distribution: DifficultyDistributionIn = Field(default_factory=DifficultyDistributionIn)
    total_questions: int = 30


class ClassroomEntryTestCreateOut(BaseModel):
    assessment_id: int
    preview_url: str
