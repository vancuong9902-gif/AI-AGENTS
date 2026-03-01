"""add topic_material_cache

Revision ID: 0a9b8c7d6e5f
Revises: f1a2b3c4d5e7
Create Date: 2026-03-01 06:25:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '0a9b8c7d6e5f'
down_revision = 'f1a2b3c4d5e7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'topic_material_cache',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('topic_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['topic_id'], ['document_topics.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('topic_id', name='uq_topic_material_cache_topic_id'),
    )
    op.create_index(op.f('ix_topic_material_cache_document_id'), 'topic_material_cache', ['document_id'], unique=False)
    op.create_index(op.f('ix_topic_material_cache_topic_id'), 'topic_material_cache', ['topic_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_topic_material_cache_topic_id'), table_name='topic_material_cache')
    op.drop_index(op.f('ix_topic_material_cache_document_id'), table_name='topic_material_cache')
    op.drop_table('topic_material_cache')
