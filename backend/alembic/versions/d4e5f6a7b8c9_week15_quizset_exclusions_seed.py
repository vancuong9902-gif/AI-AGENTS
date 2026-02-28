"""week15 quizset exclusions seed

Revision ID: d4e5f6a7b8c9
Revises: c2d9b0a2b5ef
Create Date: 2026-02-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c2d9b0a2b5ef'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('quiz_sets', sa.Column('excluded_from_quiz_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column('quiz_sets', sa.Column('generation_seed', sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column('quiz_sets', 'generation_seed')
    op.drop_column('quiz_sets', 'excluded_from_quiz_ids')
