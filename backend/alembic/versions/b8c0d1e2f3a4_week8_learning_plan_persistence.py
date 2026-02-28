"""week8_learning_plan_persistence

Revision ID: b8c0d1e2f3a4
Revises: a8c1d9f0e6b1
Create Date: 2026-02-11

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "b8c0d1e2f3a4"
down_revision = "a8c1d9f0e6b1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learning_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("assigned_topic", sa.String(length=255), nullable=True),
        sa.Column("level", sa.String(length=50), nullable=False, server_default="beginner"),
        sa.Column("days_total", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("minutes_per_day", sa.Integer(), nullable=False, server_default="35"),
        sa.Column("plan_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    # NOTE: user_id/teacher_id already have index=True above, which auto-creates
    # ix_learning_plans_user_id and ix_learning_plans_teacher_id. Creating them
    # again would raise DuplicateTable / relation already exists on Postgres.

    op.create_table(
        "learning_plan_task_completions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("learning_plans.id"), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column("task_index", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("plan_id", "day_index", "task_index", name="uq_plan_day_task"),
    )
    op.create_index("ix_learning_plan_task_completions_plan_id", "learning_plan_task_completions", ["plan_id"], unique=False)

    op.create_table(
        "learning_plan_homework_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("learning_plans.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("grade_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("plan_id", "user_id", "day_index", name="uq_plan_user_day"),
    )
    op.create_index(
        "ix_learning_plan_homework_submissions_plan_id",
        "learning_plan_homework_submissions",
        ["plan_id"],
        unique=False,
    )
    op.create_index(
        "ix_learning_plan_homework_submissions_user_id",
        "learning_plan_homework_submissions",
        ["user_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_learning_plan_homework_submissions_user_id", table_name="learning_plan_homework_submissions")
    op.drop_index("ix_learning_plan_homework_submissions_plan_id", table_name="learning_plan_homework_submissions")
    op.drop_table("learning_plan_homework_submissions")

    op.drop_index("ix_learning_plan_task_completions_plan_id", table_name="learning_plan_task_completions")
    op.drop_table("learning_plan_task_completions")

    op.drop_index("ix_learning_plans_teacher_id", table_name="learning_plans")
    op.drop_index("ix_learning_plans_user_id", table_name="learning_plans")
    op.drop_table("learning_plans")
