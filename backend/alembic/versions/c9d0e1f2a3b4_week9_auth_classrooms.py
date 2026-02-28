"""week9 auth + classrooms

Revision ID: c9d0e1f2a3b4
Revises: b8c0d1e2f3a4
Create Date: 2026-02-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c9d0e1f2a3b4"
down_revision = "b8c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ----- users: role, password_hash, is_active, updated_at -----
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=32), nullable=False, server_default="student"),
    )
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "users",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # ----- classrooms -----
    op.create_table(
        "classrooms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("join_code", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("join_code", name="uq_classrooms_join_code"),
    )
    op.create_index("ix_classrooms_teacher_id", "classrooms", ["teacher_id"], unique=False)
    op.create_index("ix_classrooms_join_code", "classrooms", ["join_code"], unique=True)

    op.create_table(
        "classroom_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("classroom_id", sa.Integer(), sa.ForeignKey("classrooms.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("classroom_id", "user_id", name="uq_classroom_user"),
    )
    op.create_index("ix_classroom_members_classroom_id", "classroom_members", ["classroom_id"], unique=False)
    op.create_index("ix_classroom_members_user_id", "classroom_members", ["user_id"], unique=False)

    # ----- learning_plans: classroom_id -----
    op.add_column(
        "learning_plans",
        sa.Column("classroom_id", sa.Integer(), sa.ForeignKey("classrooms.id"), nullable=True),
    )
    op.create_index("ix_learning_plans_classroom_id", "learning_plans", ["classroom_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_learning_plans_classroom_id", table_name="learning_plans")
    op.drop_column("learning_plans", "classroom_id")

    op.drop_index("ix_classroom_members_user_id", table_name="classroom_members")
    op.drop_index("ix_classroom_members_classroom_id", table_name="classroom_members")
    op.drop_table("classroom_members")

    op.drop_index("ix_classrooms_join_code", table_name="classrooms")
    op.drop_index("ix_classrooms_teacher_id", table_name="classrooms")
    op.drop_table("classrooms")

    op.drop_column("users", "updated_at")
    op.drop_column("users", "is_active")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "role")