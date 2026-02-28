"""week7 document topics

Revision ID: a8c1d9f0e6b1
Revises: d4a1f2c7e8b9
Create Date: 2026-02-08

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "a8c1d9f0e6b1"
down_revision = "d4a1f2c7e8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("topic_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "keywords",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("start_chunk_index", sa.Integer(), nullable=True),
        sa.Column("end_chunk_index", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_document_topics_document_id",
        "document_topics",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_topics_document_id", table_name="document_topics")
    op.drop_table("document_topics")
