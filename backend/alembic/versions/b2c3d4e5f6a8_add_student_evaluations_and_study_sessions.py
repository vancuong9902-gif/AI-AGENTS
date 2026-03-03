"""add student evaluations and study sessions

Revision ID: b2c3d4e5f6a8
Revises: d9e8f7a6b5c4
Create Date: 2026-03-03 00:00:01.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6a8"
down_revision = "d9e8f7a6b5c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("classroom_id", sa.Integer(), sa.ForeignKey("classrooms.id"), nullable=False),
        sa.Column("evaluation_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("grade", sa.String(length=20), nullable=False, server_default="Trung bình"),
        sa.Column("placement_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("final_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ai_generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("reviewed_by_teacher", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_student_evaluations_student_id", "student_evaluations", ["student_id"])
    op.create_index("ix_student_evaluations_classroom_id", "student_evaluations", ["classroom_id"])

    op.create_table(
        "study_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("classrooms.id"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("activity_type", sa.String(length=50), nullable=False, server_default="reading"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_study_sessions_student_id", "study_sessions", ["student_id"])
    op.create_index("ix_study_sessions_course_id", "study_sessions", ["course_id"])


def downgrade() -> None:
    op.drop_index("ix_study_sessions_course_id", table_name="study_sessions")
    op.drop_index("ix_study_sessions_student_id", table_name="study_sessions")
    op.drop_table("study_sessions")

    op.drop_index("ix_student_evaluations_classroom_id", table_name="student_evaluations")
    op.drop_index("ix_student_evaluations_student_id", table_name="student_evaluations")
    op.drop_table("student_evaluations")
