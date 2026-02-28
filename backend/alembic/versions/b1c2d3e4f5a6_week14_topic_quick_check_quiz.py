"""week14 topic quick check quiz link

Revision ID: b1c2d3e4f5a6
Revises: 9a7b6c5d4e3f
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa


revision = "b1c2d3e4f5a6"
down_revision = "9a7b6c5d4e3f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_topics",
        sa.Column("quick_check_quiz_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_document_topics_quick_check_quiz_id",
        "document_topics",
        ["quick_check_quiz_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_document_topics_quick_check_quiz_id",
        "document_topics",
        "quiz_sets",
        ["quick_check_quiz_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_document_topics_quick_check_quiz_id", "document_topics", type_="foreignkey")
    op.drop_index("ix_document_topics_quick_check_quiz_id", table_name="document_topics")
    op.drop_column("document_topics", "quick_check_quiz_id")
