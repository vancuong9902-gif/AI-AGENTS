"""week16 teacher review topics

Revision ID: c4d5e6f7a8b9
Revises: b1c2d3e4f5a6
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa


revision = "c4d5e6f7a8b9"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


review_status = sa.Enum("pending_review", "approved", "rejected", "edited", name="document_topic_review_status")


def upgrade() -> None:
    bind = op.get_bind()
    review_status.create(bind, checkfirst=True)

    op.add_column(
        "document_topics",
        sa.Column("status", review_status, nullable=False, server_default="pending_review"),
    )
    op.add_column("document_topics", sa.Column("teacher_edited_title", sa.String(length=255), nullable=True))
    op.add_column("document_topics", sa.Column("teacher_note", sa.Text(), nullable=True))
    op.add_column("document_topics", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_document_topics_status", "document_topics", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_document_topics_status", table_name="document_topics")
    op.drop_column("document_topics", "reviewed_at")
    op.drop_column("document_topics", "teacher_note")
    op.drop_column("document_topics", "teacher_edited_title")
    op.drop_column("document_topics", "status")

    bind = op.get_bind()
    review_status.drop(bind, checkfirst=True)
