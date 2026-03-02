from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class StudentLevel(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


@dataclass(slots=True)
class Topic:
    id: str
    title: str
    summary: str
    difficulty: float
    keywords: list[str]


@dataclass(slots=True)
class EntranceTestQuestion:
    id: str
    topic_id: str
    stem: str
    choices: list[str]
    answer_index: int
    difficulty: float


@dataclass(slots=True)
class LearningPathStep:
    order: int
    topic_id: str
    objective: str
    exercise_count: int


@dataclass(slots=True)
class ProgressSnapshot:
    student_id: str
    completion_rate: float
    mastery_by_topic: dict[str, float]
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class PerformanceReport:
    student_id: str
    level: StudentLevel
    strengths: list[str]
    weaknesses: list[str]
    recommendations: list[str]
    metrics: dict[str, Any]
