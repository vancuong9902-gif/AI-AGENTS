from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ClassroomCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    course_id: Optional[int] = None


class ClassroomOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    invite_code: str
    join_code: Optional[str] = None
    teacher_id: int
    course_id: Optional[int] = None
    is_active: bool = True
    student_count: int = 0
    created_at: Optional[datetime] = None


class ClassroomJoinRequest(BaseModel):
    invite_code: str = Field(min_length=8, max_length=8)


class ClassroomStudentOut(BaseModel):
    id: int
    full_name: Optional[str] = None
    email: str
    joined_at: Optional[datetime] = None
    placement_score: Optional[float] = None
    final_score: Optional[float] = None
    level: Optional[str] = None


class ClassroomSubjectOut(BaseModel):
    id: int
    title: str
    summary: Optional[str] = None


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
