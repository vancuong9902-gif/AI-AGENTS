"""notifications payload_json alignment

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e7
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a1b2c3d4e5f6"
down_revision = "f1a2b3c4d5e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in op.get_bind().dialect.get_columns(op.get_bind(), "notifications")}
    if "payload_json" not in columns:
        op.add_column(
            "notifications",
            sa.Column(
                "payload_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )
    if "data" in columns:
        op.execute("UPDATE notifications SET payload_json = COALESCE(data::jsonb, '{}'::jsonb)")
        op.drop_column("notifications", "data")


def downgrade() -> None:
    columns = {c["name"] for c in op.get_bind().dialect.get_columns(op.get_bind(), "notifications")}
    if "data" not in columns:
        op.add_column(
            "notifications",
            sa.Column(
                "data",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )
    if "payload_json" in columns:
        op.execute("UPDATE notifications SET data = COALESCE(payload_json::jsonb, '{}'::jsonb)")
        op.drop_column("notifications", "payload_json")
