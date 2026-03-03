from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class Classroom(Base):
    __tablename__ = "classrooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    course_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("mvp_courses.id"), nullable=True, index=True)
    invite_code: Mapped[str] = mapped_column(String(8), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def join_code(self) -> str:
        return self.invite_code

    @join_code.setter
    def join_code(self, value: str) -> None:
        self.invite_code = value


class ClassroomStudent(Base):
    __tablename__ = "classroom_students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    classroom_id: Mapped[int] = mapped_column(Integer, ForeignKey("classrooms.id"), index=True)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    placement_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    level: Mapped[str | None] = mapped_column(String(20), nullable=True)

    __table_args__ = (UniqueConstraint("classroom_id", "student_id", name="uq_classroom_student"),)

    @property
    def user_id(self) -> int:
        return self.student_id

    @user_id.setter
    def user_id(self, value: int) -> None:
        self.student_id = value


ClassroomMember = ClassroomStudent
