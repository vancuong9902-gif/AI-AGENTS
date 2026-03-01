"""week17 topic draft publish fields

Revision ID: a9b8c7d6e5f4
Revises: f7a8b9c0d1e2
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'a9b8c7d6e5f4'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('document_topics', sa.Column('edited_title', sa.String(length=255), nullable=True))
    op.add_column(
        'document_topics',
        sa.Column('meta_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    op.execute("ALTER TABLE document_topics ALTER COLUMN status TYPE VARCHAR(20) USING status::text")
    op.execute("ALTER TABLE document_topics ALTER COLUMN status SET DEFAULT 'published'")
    op.execute("UPDATE document_topics SET status='published' WHERE status IN ('pending_review','approved','edited') OR status IS NULL")


def downgrade() -> None:
    op.execute("UPDATE document_topics SET status='approved' WHERE status='published'")
    op.execute(
        "ALTER TABLE document_topics ALTER COLUMN status TYPE document_topic_review_status USING "
        "(CASE WHEN status IN ('approved','rejected','edited','pending_review') THEN status ELSE 'approved' END)::document_topic_review_status"
    )
    op.execute("ALTER TABLE document_topics ALTER COLUMN status SET DEFAULT 'pending_review'")

    op.drop_column('document_topics', 'meta_json')
    op.drop_column('document_topics', 'edited_title')
