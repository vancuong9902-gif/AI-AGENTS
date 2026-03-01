"""add session heartbeat snapshot lock fields

Revision ID: 3b4c5d6e7f8a
Revises: e6f7a8b9c0d1
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "3b4c5d6e7f8a"
down_revision = "e6f7a8b9c0d1"
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
    op.add_column("sessions", sa.Column("linked_attempt_record_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_sessions_linked_attempt_record_id_attempts",
        "sessions",
        "attempts",
        ["linked_attempt_record_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_sessions_linked_attempt_record_id_attempts", "sessions", type_="foreignkey")
    op.drop_column("sessions", "linked_attempt_record_id")
    op.drop_column("sessions", "locked_at")
    op.drop_column("sessions", "answers_snapshot_json")
    op.drop_column("sessions", "last_heartbeat_at")
