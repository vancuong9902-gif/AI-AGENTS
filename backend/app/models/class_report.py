from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class ClassReport(Base):
    __tablename__ = "class_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    classroom_id: Mapped[int] = mapped_column(ForeignKey("classrooms.id", ondelete="CASCADE"), index=True, nullable=False)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("quiz_sets.id", ondelete="CASCADE"), index=True, nullable=False)

    narrative: Mapped[str] = mapped_column(nullable=False, default="")
    stats_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    improvement_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("classroom_id", "assessment_id", name="uq_class_report_classroom_assessment"),
    )
