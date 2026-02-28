from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class ClassroomAssessment(Base):
    __tablename__ = "classroom_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)

    classroom_id: Mapped[int] = mapped_column(
        ForeignKey("classrooms.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_sets.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("classroom_id", "assessment_id", name="uq_classroom_assessment"),
    )
