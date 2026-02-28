"""week14 quiz duration seconds and topic metadata

Revision ID: 7c9e1a2b3d4f
Revises: 1e2f3a4b5c6d, a1b2c3d4e5f6
Create Date: 2026-02-28

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "7c9e1a2b3d4f"
down_revision = ("1e2f3a4b5c6d", "a1b2c3d4e5f6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quiz_sets",
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default=sa.text("1800")),
    )

    op.execute(
        """
        UPDATE quiz_sets
        SET duration_seconds = CAST(SPLIT_PART(level,'duration=',2) AS INT)
        WHERE level LIKE '%duration=%'
        """
    )

    op.add_column(
        "document_topics",
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("document_topics", "metadata_json")
    op.drop_column("quiz_sets", "duration_seconds")
