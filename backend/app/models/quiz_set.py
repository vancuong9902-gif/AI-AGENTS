from __future__ import annotations

from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class QuizSet(Base):
    __tablename__ = "quiz_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="quiz",
        server_default=text("'quiz'"),
    )
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[str] = mapped_column(String(50), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1800"))
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    source_query_id: Mapped[int | None] = mapped_column(ForeignKey("rag_queries.id"), nullable=True)
    excluded_from_quiz_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    generation_seed: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
