"""add session heartbeat snapshot lock fields

Revision ID: 3b4c5d6e7f8a
Revises: e6f7a8b9c0d1
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "3b4c5d6e7f8a"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    session_columns = {col["name"] for col in inspector.get_columns("sessions")}

    if "last_heartbeat_at" not in session_columns:
        op.add_column("sessions", sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    if "answers_snapshot_json" not in session_columns:
        op.add_column(
            "sessions",
            sa.Column(
                "answers_snapshot_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )
    if "locked_at" not in session_columns:
        op.add_column("sessions", sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True))
    if "linked_attempt_record_id" not in session_columns:
        op.add_column("sessions", sa.Column("linked_attempt_record_id", sa.Integer(), nullable=True))

    foreign_key_names = {fk["name"] for fk in inspector.get_foreign_keys("sessions")}
    if "fk_sessions_linked_attempt_record_id_attempts" not in foreign_key_names:
        op.create_foreign_key(
            "fk_sessions_linked_attempt_record_id_attempts",
            "sessions",
            "attempts",
            ["linked_attempt_record_id"],
            ["id"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    foreign_key_names = {fk["name"] for fk in inspector.get_foreign_keys("sessions")}
    if "fk_sessions_linked_attempt_record_id_attempts" in foreign_key_names:
        op.drop_constraint("fk_sessions_linked_attempt_record_id_attempts", "sessions", type_="foreignkey")

    session_columns = {col["name"] for col in inspector.get_columns("sessions")}
    if "linked_attempt_record_id" in session_columns:
        op.drop_column("sessions", "linked_attempt_record_id")
    if "locked_at" in session_columns:
        op.drop_column("sessions", "locked_at")
    if "answers_snapshot_json" in session_columns:
        op.drop_column("sessions", "answers_snapshot_json")
    if "last_heartbeat_at" in session_columns:
        op.drop_column("sessions", "last_heartbeat_at")
