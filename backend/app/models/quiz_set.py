from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func, text
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
    source_query_id: Mapped[int | None] = mapped_column(ForeignKey("rag_queries.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
