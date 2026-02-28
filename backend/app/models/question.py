from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base_class import Base


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_set_id: Mapped[int] = mapped_column(ForeignKey("quiz_sets.id"), index=True, nullable=False)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="mcq")
    # Bloom level (6-level taxonomy) for analytics / adaptive learning
    # remember | understand | apply | analyze | evaluate | create
    bloom_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="understand",
        server_default=text("'understand'"),
    )
    stem: Mapped[str] = mapped_column(Text, nullable=False)

    # MCQ fields
    options: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    correct_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Essay fields (type="essay")
    max_points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    rubric: Mapped[list[dict]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Recommended time (minutes) for this question.
    # Estimated by the system (LLM when available, otherwise heuristics) and used
    # for building a time limit for timed assessments.
    estimated_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    sources: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
