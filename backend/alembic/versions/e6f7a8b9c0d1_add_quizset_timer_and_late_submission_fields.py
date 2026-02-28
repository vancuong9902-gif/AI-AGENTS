"""add quizset timer and late submission fields

Revision ID: e6f7a8b9c0d1
Revises: 1f2e3d4c5b6a, c1a2b3d4e5f6, c4d5e6f7a8b9
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e6f7a8b9c0d1"
down_revision = ("1f2e3d4c5b6a", "c1a2b3d4e5f6", "c4d5e6f7a8b9")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quiz_sets", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("quiz_sets", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("quiz_sets", sa.Column("time_limit_seconds", sa.Integer(), nullable=False, server_default="0"))

    op.add_column("attempts", sa.Column("is_late", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("attempts", sa.Column("late_by_seconds", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("attempts", "late_by_seconds")
    op.drop_column("attempts", "is_late")
    op.drop_column("quiz_sets", "time_limit_seconds")
    op.drop_column("quiz_sets", "submitted_at")
    op.drop_column("quiz_sets", "started_at")
