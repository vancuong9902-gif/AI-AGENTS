from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class LearningPlan(Base):
    """Persisted teacher-style learning plan.

    Why a separate table?
    - We avoid altering existing core tables (no migrations needed for existing DB volumes).
    - Plans can be regenerated and compared over time.
    """

    __tablename__ = "learning_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    teacher_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Optional class context (B9)
    classroom_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("classrooms.id"), nullable=True, index=True)

    assigned_topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    level: Mapped[str] = mapped_column(String(50), nullable=False, default="beginner")
    days_total: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    minutes_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=35)

    # Stored as the TeacherLearningPlan schema dict.
    plan_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LearningPlanTaskCompletion(Base):
    __tablename__ = "learning_plan_task_completions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("learning_plans.id"), index=True)
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    task_index: Mapped[int] = mapped_column(Integer, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("plan_id", "day_index", "task_index", name="uq_plan_day_task"),)


class LearningPlanHomeworkSubmission(Base):
    __tablename__ = "learning_plan_homework_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("learning_plans.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)

    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional structured answers (e.g., MCQ choices) for mixed homework.
    answer_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    grade_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("plan_id", "user_id", "day_index", name="uq_plan_user_day"),)
