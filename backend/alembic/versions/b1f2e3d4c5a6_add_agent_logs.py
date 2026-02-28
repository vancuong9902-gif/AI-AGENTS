"""add agent logs

Revision ID: b1f2e3d4c5a6
Revises: 7c9e1a2b3d4f, 9a7b6c5d4e3f, 9c7e1a2b3d4f
Create Date: 2026-02-28 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b1f2e3d4c5a6"
down_revision: Union[str, Sequence[str], None] = ("7c9e1a2b3d4f", "9a7b6c5d4e3f", "9c7e1a2b3d4f")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("agent_name", sa.String(length=120), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("input_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_logs_event_id"), "agent_logs", ["event_id"], unique=False)
    op.create_index(op.f("ix_agent_logs_user_id"), "agent_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_logs_user_id"), table_name="agent_logs")
    op.drop_index(op.f("ix_agent_logs_event_id"), table_name="agent_logs")
    op.drop_table("agent_logs")
