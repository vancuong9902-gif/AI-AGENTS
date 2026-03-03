from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class StudentEvaluation(Base):
    __tablename__ = "student_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    classroom_id: Mapped[int] = mapped_column(ForeignKey("classrooms.id"), index=True, nullable=False)
    evaluation_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    grade: Mapped[str] = mapped_column(String(20), nullable=False, default="Trung bình")
    placement_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    final_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ai_generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_by_teacher: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
