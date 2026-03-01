from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base_class import Base


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    quiz_set_id: Mapped[int] = mapped_column(ForeignKey("quiz_sets.id"), index=True, nullable=False)
    score_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    answers_json: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    breakdown_json: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    explanation_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    duration_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_late: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    late_by_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deadline_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
