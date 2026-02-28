"""week3 schema: diagnostic_attempts (pre/post)

Revision ID: 6b6e9c8e4d7a
Revises: 2f3b7c2f0b0a
Create Date: 2026-01-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "6b6e9c8e4d7a"
down_revision: Union[str, Sequence[str], None] = "2f3b7c2f0b0a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=20), server_default="pre", nullable=False),
        sa.Column("score_percent", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("correct_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("level", sa.String(length=50), server_default="beginner", nullable=False),
        sa.Column("answers_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_diagnostic_attempts_user_id"), "diagnostic_attempts", ["user_id"], unique=False)
    op.create_index(op.f("ix_diagnostic_attempts_stage"), "diagnostic_attempts", ["stage"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_diagnostic_attempts_stage"), table_name="diagnostic_attempts")
    op.drop_index(op.f("ix_diagnostic_attempts_user_id"), table_name="diagnostic_attempts")
    op.drop_table("diagnostic_attempts")
