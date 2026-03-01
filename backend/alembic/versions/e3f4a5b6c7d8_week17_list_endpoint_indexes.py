"""week17 list endpoint indexes

Revision ID: e3f4a5b6c7d8
Revises: 0a9b8c7d6e5f
Create Date: 2026-03-01 00:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = 'e3f4a5b6c7d8'
down_revision = '0a9b8c7d6e5f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        'ix_documents_user_id_created_at',
        'documents',
        ['user_id', 'created_at'],
        unique=False,
    )
    op.create_index(
        'ix_document_topics_document_id_page_start_topic_index',
        'document_topics',
        ['document_id', 'page_start', 'topic_index'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_document_topics_document_id_page_start_topic_index', table_name='document_topics')
    op.drop_index('ix_documents_user_id_created_at', table_name='documents')
