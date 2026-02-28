from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class StudentAssignment(Base):
    __tablename__ = "student_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    classroom_id: Mapped[int] = mapped_column(ForeignKey("classrooms.id"), index=True, nullable=False)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("document_topics.id"), nullable=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True, nullable=False)
    assignment_type: Mapped[str] = mapped_column(String(32), nullable=False)  # reading/exercise/quiz_practice/essay_case_study
    student_level: Mapped[str] = mapped_column(String(32), nullable=False)  # gioi/kha/trung_binh/yeu
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
