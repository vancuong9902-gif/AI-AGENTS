"""add quiz sessions timer enforcement

Revision ID: c1a2b3d4e5f6
Revises: aa12bb34cc56, b1f2e3d4c5a6, d4e5f6a7b8c9, e3f4a5b6c7d8, f7a8b9c0d1e2
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c1a2b3d4e5f6"
down_revision = ("aa12bb34cc56", "b1f2e3d4c5a6", "d4e5f6a7b8c9", "e3f4a5b6c7d8", "f7a8b9c0d1e2")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quiz_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("quiz_set_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_limit_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["quiz_set_id"], ["quiz_sets.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quiz_set_id", "user_id", name="uq_quiz_sessions_quiz_user"),
    )
    op.create_index(op.f("ix_quiz_sessions_quiz_set_id"), "quiz_sessions", ["quiz_set_id"], unique=False)
    op.create_index(op.f("ix_quiz_sessions_user_id"), "quiz_sessions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_quiz_sessions_user_id"), table_name="quiz_sessions")
    op.drop_index(op.f("ix_quiz_sessions_quiz_set_id"), table_name="quiz_sessions")
    op.drop_table("quiz_sessions")
