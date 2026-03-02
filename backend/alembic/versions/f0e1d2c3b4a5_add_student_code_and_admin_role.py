"""add student_code and admin-role support

Revision ID: f0e1d2c3b4a5
Revises: e3f4a5b6c7d8
Create Date: 2026-03-02
"""

from alembic import op
import sqlalchemy as sa


revision = 'f0e1d2c3b4a5'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('student_code', sa.String(length=64), nullable=True))
    op.create_index('ix_users_student_code', 'users', ['student_code'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_users_student_code', table_name='users')
    op.drop_column('users', 'student_code')
