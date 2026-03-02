"""add mvp tables

Revision ID: d9e8f7a6b5c4
Revises: c0eed4ba67ff
Create Date: 2026-03-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d9e8f7a6b5c4"
down_revision = "c0eed4ba67ff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mvp_courses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_mvp_courses_teacher_id"), "mvp_courses", ["teacher_id"], unique=False)

    op.create_table(
        "mvp_topics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("exercises_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["mvp_courses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_mvp_topics_course_id"), "mvp_topics", ["course_id"], unique=False)

    op.create_table(
        "mvp_exams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["course_id"], ["mvp_courses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_mvp_exams_course_id"), "mvp_exams", ["course_id"], unique=False)

    op.create_table(
        "mvp_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("options_json", sa.Text(), nullable=False),
        sa.Column("answer", sa.String(length=255), nullable=False),
        sa.Column("difficulty", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["exam_id"], ["mvp_exams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_mvp_questions_exam_id"), "mvp_questions", ["exam_id"], unique=False)

    op.create_table(
        "mvp_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("level", sa.String(length=32), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["exam_id"], ["mvp_exams.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_mvp_results_exam_id"), "mvp_results", ["exam_id"], unique=False)
    op.create_index(op.f("ix_mvp_results_student_id"), "mvp_results", ["student_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_mvp_results_student_id"), table_name="mvp_results")
    op.drop_index(op.f("ix_mvp_results_exam_id"), table_name="mvp_results")
    op.drop_table("mvp_results")

    op.drop_index(op.f("ix_mvp_questions_exam_id"), table_name="mvp_questions")
    op.drop_table("mvp_questions")

    op.drop_index(op.f("ix_mvp_exams_course_id"), table_name="mvp_exams")
    op.drop_table("mvp_exams")

    op.drop_index(op.f("ix_mvp_topics_course_id"), table_name="mvp_topics")
    op.drop_table("mvp_topics")

    op.drop_index(op.f("ix_mvp_courses_teacher_id"), table_name="mvp_courses")
    op.drop_table("mvp_courses")
