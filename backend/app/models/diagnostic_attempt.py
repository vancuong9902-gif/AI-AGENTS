from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base_class import Base


class DiagnosticAttempt(Base):
    __tablename__ = "diagnostic_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    # "pre" (đầu vào) hoặc "post" (cuối kỳ)
    stage: Mapped[str] = mapped_column(String(20), index=True, nullable=False, default="pre")


    # Liên kết với bài hybrid Assessment/Diagnostic
    assessment_id: Mapped[int | None] = mapped_column(ForeignKey("quiz_sets.id"), index=True, nullable=True)
    attempt_id: Mapped[int | None] = mapped_column(ForeignKey("attempts.id"), index=True, nullable=True)

    # Điểm tách (0–100)
    mcq_score_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    essay_score_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Mastery theo topic + metadata (vd: weak_topics)
    mastery_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    score_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    level: Mapped[str] = mapped_column(String(50), nullable=False, default="beginner")

    answers_json: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
