"""week10 classroom_assessments mapping

Revision ID: d1a2b3c4d5e6
Revises: c9d0e1f2a3b4
Create Date: 2026-02-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d1a2b3c4d5e6"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "classroom_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("classroom_id", sa.Integer(), sa.ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assessment_id", sa.Integer(), sa.ForeignKey("quiz_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("classroom_id", "assessment_id", name="uq_classroom_assessment"),
    )
    op.create_index("ix_classroom_assessments_classroom_id", "classroom_assessments", ["classroom_id"])
    op.create_index("ix_classroom_assessments_assessment_id", "classroom_assessments", ["assessment_id"])


def downgrade() -> None:
    op.drop_index("ix_classroom_assessments_assessment_id", table_name="classroom_assessments")
    op.drop_index("ix_classroom_assessments_classroom_id", table_name="classroom_assessments")
    op.drop_table("classroom_assessments")
