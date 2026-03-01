"""add_attempt_explanation_json

Revision ID: c7d8e9f0a1b2
Revises: ab12cd34ef56
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c7d8e9f0a1b2"
down_revision = "ab12cd34ef56"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "attempts",
        sa.Column("explanation_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade():
    op.drop_column("attempts", "explanation_json")
