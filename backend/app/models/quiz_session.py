from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class QuizSession(Base):
    __tablename__ = "quiz_sessions"
    __table_args__ = (UniqueConstraint("quiz_set_id", "user_id", name="uq_quiz_sessions_quiz_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_set_id: Mapped[int] = mapped_column(ForeignKey("quiz_sets.id"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_limit_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
