"""week16 topic publish flags

Revision ID: f1a2b3c4d5e7
Revises: e6f7a8b9c0d1
Create Date: 2026-02-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e7'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('document_topics', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.add_column('document_topics', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')))
    op.create_index('ix_document_topics_is_active', 'document_topics', ['is_active'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_document_topics_is_active', table_name='document_topics')
    op.drop_column('document_topics', 'updated_at')
    op.drop_column('document_topics', 'is_active')
