"""week13 topic validation fields

Revision ID: 1e2f3a4b5c6d
Revises: 0b7a3c9d1e2f
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa


revision = "1e2f3a4b5c6d"
down_revision = "0b7a3c9d1e2f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_topics", sa.Column("display_title", sa.String(length=255), nullable=False, server_default=sa.text("''")))
    op.add_column("document_topics", sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("document_topics", sa.Column("extraction_confidence", sa.Float(), nullable=False, server_default=sa.text("0")))
    op.add_column("document_topics", sa.Column("page_start", sa.Integer(), nullable=True))
    op.add_column("document_topics", sa.Column("page_end", sa.Integer(), nullable=True))

    op.execute("UPDATE document_topics SET display_title = title WHERE COALESCE(display_title, '') = ''")

    op.create_index(
        "ix_document_topics_document_id_page_start",
        "document_topics",
        ["document_id", "page_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_topics_document_id_page_start", table_name="document_topics")
    op.drop_column("document_topics", "page_end")
    op.drop_column("document_topics", "page_start")
    op.drop_column("document_topics", "extraction_confidence")
    op.drop_column("document_topics", "needs_review")
    op.drop_column("document_topics", "display_title")
