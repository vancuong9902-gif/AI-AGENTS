"""week15 entry test metadata + classroom visibility

Revision ID: e3f4a5b6c7d8
Revises: 7c9e1a2b3d4f, 9a7b6c5d4e3f, 9c7e1a2b3d4f
Create Date: 2026-02-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e3f4a5b6c7d8"
down_revision = ("7c9e1a2b3d4f", "9a7b6c5d4e3f", "9c7e1a2b3d4f")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quiz_sets",
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )

    op.add_column(
        "classroom_assessments",
        sa.Column("kind", sa.String(length=50), nullable=False, server_default=sa.text("'midterm'")),
    )
    op.add_column(
        "classroom_assessments",
        sa.Column("visible_to_students", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("classroom_assessments", "visible_to_students")
    op.drop_column("classroom_assessments", "kind")
    op.drop_column("quiz_sets", "metadata_json")
