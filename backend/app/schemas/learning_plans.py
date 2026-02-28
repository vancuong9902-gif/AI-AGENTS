from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.schemas.profile import TeacherLearningPlan


class LearningPlanLatestResponse(BaseModel):
    plan_id: int
    user_id: int
    teacher_id: Optional[int] = None
    classroom_id: Optional[int] = None
    assigned_topic: Optional[str] = None
    level: str = "beginner"
    days_total: int = 7
    minutes_per_day: int = 35
    teacher_plan: TeacherLearningPlan

    # persisted state
    task_completion: Dict[str, bool] = Field(default_factory=dict)  # key: "day:task"
    homework_submissions: Dict[int, Dict[str, Any]] = Field(default_factory=dict)  # day_index -> grade_json


class TaskCompleteRequest(BaseModel):
    day_index: int
    task_index: int
    completed: bool = True


class HomeworkGradeFromPlanRequest(BaseModel):
    user_id: int
    day_index: int
    # Essay answer (optional when homework contains only MCQ)
    answer_text: str = ""
    # MCQ answers: {question_id: chosen_index}
    mcq_answers: Dict[str, int] = Field(default_factory=dict)
