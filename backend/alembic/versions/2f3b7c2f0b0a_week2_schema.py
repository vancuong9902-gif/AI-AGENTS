"""week2 schema: chunks, rag_queries, quiz_sets/questions/attempts, learner_profiles

Revision ID: 2f3b7c2f0b0a
Revises: efde99579f1b
Create Date: 2026-01-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '2f3b7c2f0b0a'
down_revision: Union[str, Sequence[str], None] = 'efde99579f1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # documents: add metadata columns
    op.add_column('documents', sa.Column('filename', sa.String(length=255), server_default='unknown', nullable=False))
    op.add_column('documents', sa.Column('mime_type', sa.String(length=255), server_default='application/octet-stream', nullable=False))
    op.add_column('documents', sa.Column('tags', postgresql.ARRAY(sa.String()), server_default=sa.text("'{}'::text[]"), nullable=False))

    # create document_chunks
    op.create_table(
        'document_chunks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_document_chunks_document_id'), 'document_chunks', ['document_id'], unique=False)

    # rag_queries
    op.create_table(
        'rag_queries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('top_k', sa.Integer(), server_default=sa.text('5'), nullable=False),
        sa.Column('filters', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('result_chunk_ids', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # learner_profiles
    op.create_table(
        'learner_profiles',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('level', sa.String(length=50), server_default='beginner', nullable=False),
        sa.Column('mastery_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('user_id'),
    )

    # keep week1 tables as legacy to avoid breaking future migrations
    op.rename_table('quizzes', 'quizzes_legacy')
    op.rename_table('attempts', 'attempts_legacy')

    # IMPORTANT (PostgreSQL): renaming a table does NOT rename its indexes.
    # The init migration created indexes named ix_attempts_user_id / ix_attempts_quiz_id.
    # If we create a new attempts table and try to reuse the same index names, Postgres will error.
    op.execute("ALTER INDEX IF EXISTS ix_attempts_user_id RENAME TO ix_attempts_legacy_user_id")
    op.execute("ALTER INDEX IF EXISTS ix_attempts_quiz_id RENAME TO ix_attempts_legacy_quiz_id")

    # quiz_sets
    op.create_table(
        'quiz_sets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('topic', sa.String(length=255), nullable=False),
        sa.Column('level', sa.String(length=50), nullable=False),
        sa.Column('source_query_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['source_query_id'], ['rag_queries.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_quiz_sets_user_id'), 'quiz_sets', ['user_id'], unique=False)

    # questions
    op.create_table(
        'questions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('quiz_set_id', sa.Integer(), nullable=False),
        sa.Column('order_no', sa.Integer(), server_default=sa.text('0'), nullable=False),
        # NOTE: PostgreSQL string literal must use single quotes.
        # Using double quotes ("mcq") is treated as an identifier and breaks migration.
        sa.Column('type', sa.String(length=50), server_default=sa.text("'mcq'"), nullable=False),
        sa.Column('stem', sa.Text(), nullable=False),
        sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('correct_index', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('sources', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['quiz_set_id'], ['quiz_sets.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_questions_quiz_set_id'), 'questions', ['quiz_set_id'], unique=False)

    # attempts (week2)
    op.create_table(
        'attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('quiz_set_id', sa.Integer(), nullable=False),
        sa.Column('score_percent', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('answers_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('breakdown_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('duration_sec', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['quiz_set_id'], ['quiz_sets.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_attempts_user_id'), 'attempts', ['user_id'], unique=False)
    op.create_index(op.f('ix_attempts_quiz_set_id'), 'attempts', ['quiz_set_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_attempts_quiz_set_id'), table_name='attempts')
    op.drop_index(op.f('ix_attempts_user_id'), table_name='attempts')
    op.drop_table('attempts')

    op.drop_index(op.f('ix_questions_quiz_set_id'), table_name='questions')
    op.drop_table('questions')

    op.drop_index(op.f('ix_quiz_sets_user_id'), table_name='quiz_sets')
    op.drop_table('quiz_sets')

    op.rename_table('attempts_legacy', 'attempts')
    op.rename_table('quizzes_legacy', 'quizzes')

    # restore original index names on legacy attempts
    op.execute("ALTER INDEX IF EXISTS ix_attempts_legacy_user_id RENAME TO ix_attempts_user_id")
    op.execute("ALTER INDEX IF EXISTS ix_attempts_legacy_quiz_id RENAME TO ix_attempts_quiz_id")

    op.drop_table('learner_profiles')
    op.drop_table('rag_queries')
    op.drop_index(op.f('ix_document_chunks_document_id'), table_name='document_chunks')
    op.drop_table('document_chunks')

    op.drop_column('documents', 'tags')
    op.drop_column('documents', 'mime_type')
    op.drop_column('documents', 'filename')
