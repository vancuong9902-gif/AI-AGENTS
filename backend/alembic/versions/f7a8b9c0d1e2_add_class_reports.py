"""add_class_reports

Revision ID: f7a8b9c0d1e2
Revises: f2c3d4e5f6a7
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f7a8b9c0d1e2"
down_revision = "f2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "class_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("classroom_id", sa.Integer(), nullable=False),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("stats_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("improvement_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["assessment_id"], ["quiz_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["classroom_id"], ["classrooms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("classroom_id", "assessment_id", name="uq_class_report_classroom_assessment"),
    )
    op.create_index(op.f("ix_class_reports_classroom_id"), "class_reports", ["classroom_id"], unique=False)
    op.create_index(op.f("ix_class_reports_assessment_id"), "class_reports", ["assessment_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_class_reports_assessment_id"), table_name="class_reports")
    op.drop_index(op.f("ix_class_reports_classroom_id"), table_name="class_reports")
    op.drop_table("class_reports")
