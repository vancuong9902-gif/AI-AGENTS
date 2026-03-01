"""auth profile and security fields

Revision ID: 5d3c2b1a9e8f
Revises: e3f4a5b6c7d8
Create Date: 2026-03-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5d3c2b1a9e8f"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone_number", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("major", sa.String(length=120), nullable=True))
    op.add_column("users", sa.Column("class_name", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "class_name")
    op.drop_column("users", "major")
    op.drop_column("users", "phone_number")
