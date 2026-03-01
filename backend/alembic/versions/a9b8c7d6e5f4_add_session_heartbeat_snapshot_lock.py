"""add session heartbeat snapshot lock fields

Revision ID: a9b8c7d6e5f4
Revises: c1a2b3d4e5f6
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "a9b8c7d6e5f4"
down_revision = "c1a2b3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "sessions",
        sa.Column(
            "answers_snapshot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("sessions", sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("attempts", sa.Column("deadline_seconds", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("attempts", "deadline_seconds")
    op.drop_column("sessions", "locked_at")
    op.drop_column("sessions", "answers_snapshot_json")
    op.drop_column("sessions", "last_heartbeat_at")
