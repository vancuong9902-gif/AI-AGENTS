from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class NotificationType(str, Enum):
    learning_plan_ready = "learning_plan_ready"
    exam_result = "exam_result"
    report_ready = "report_ready"
    class_final_ready = "class_final_ready"
    student_final_report = "student_final_report"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type: Mapped[NotificationType | str] = mapped_column(
        SQLEnum(NotificationType, name="notification_type", native_enum=False), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Thông báo")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Backward-compatible optional fields used by existing teacher-report notification flows.
    teacher_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    student_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    quiz_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("quiz_sets.id"), index=True, nullable=True)

    @property
    def data(self) -> dict:
        return self.payload_json or {}
