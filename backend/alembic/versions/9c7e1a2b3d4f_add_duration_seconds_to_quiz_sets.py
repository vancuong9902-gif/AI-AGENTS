"""add duration seconds to quiz sets

Revision ID: 9c7e1a2b3d4f
Revises: 1e2f3a4b5c6d, a1b2c3d4e5f6
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "9c7e1a2b3d4f"
down_revision = ("1e2f3a4b5c6d", "a1b2c3d4e5f6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("quiz_sets"):
        return

    columns = {col["name"] for col in inspector.get_columns("quiz_sets")}
    if "duration_seconds" not in columns:
        op.add_column(
            "quiz_sets",
            sa.Column("duration_seconds", sa.Integer(), server_default="1800", nullable=False),
        )

    op.execute(
        """
        UPDATE quiz_sets
        SET duration_seconds = CAST(SPLIT_PART(level, 'duration=', 2) AS INT)
        WHERE level LIKE '%duration=%'
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("quiz_sets"):
        return

    columns = {col["name"] for col in inspector.get_columns("quiz_sets")}
    if "duration_seconds" in columns:
        op.drop_column("quiz_sets", "duration_seconds")
