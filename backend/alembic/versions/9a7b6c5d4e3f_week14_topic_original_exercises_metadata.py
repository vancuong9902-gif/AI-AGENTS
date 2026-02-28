"""week14 topic original exercises metadata

Revision ID: 9a7b6c5d4e3f
Revises: 1e2f3a4b5c6d
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa


revision = "9a7b6c5d4e3f"
down_revision = "1e2f3a4b5c6d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_topics",
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("document_topics", "metadata_json")
