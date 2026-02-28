"""week5 diagnostic hybrid fields

Revision ID: c2d9b0a2b5ef
Revises: 8f0d2c7a1b2c
Create Date: 2026-01-29

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "c2d9b0a2b5ef"
down_revision = "8f0d2c7a1b2c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add links to assessment/attempt + split scores + mastery
    op.add_column("diagnostic_attempts", sa.Column("assessment_id", sa.Integer(), nullable=True))
    op.add_column("diagnostic_attempts", sa.Column("attempt_id", sa.Integer(), nullable=True))
    op.add_column("diagnostic_attempts", sa.Column("mcq_score_percent", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("diagnostic_attempts", sa.Column("essay_score_percent", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column(
        "diagnostic_attempts",
        sa.Column("mastery_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )

    op.create_index(op.f("ix_diagnostic_attempts_assessment_id"), "diagnostic_attempts", ["assessment_id"], unique=False)
    op.create_index(op.f("ix_diagnostic_attempts_attempt_id"), "diagnostic_attempts", ["attempt_id"], unique=False)

    op.create_foreign_key(
        "fk_diagnostic_attempts_assessment_id_quiz_sets",
        "diagnostic_attempts",
        "quiz_sets",
        ["assessment_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_diagnostic_attempts_attempt_id_attempts",
        "diagnostic_attempts",
        "attempts",
        ["attempt_id"],
        ["id"],
    )

    # Backfill split scores for existing rows (best-effort)
    op.execute("UPDATE diagnostic_attempts SET mcq_score_percent = score_percent WHERE mcq_score_percent = 0")


def downgrade() -> None:
    op.drop_constraint("fk_diagnostic_attempts_attempt_id_attempts", "diagnostic_attempts", type_="foreignkey")
    op.drop_constraint("fk_diagnostic_attempts_assessment_id_quiz_sets", "diagnostic_attempts", type_="foreignkey")
    op.drop_index(op.f("ix_diagnostic_attempts_attempt_id"), table_name="diagnostic_attempts")
    op.drop_index(op.f("ix_diagnostic_attempts_assessment_id"), table_name="diagnostic_attempts")

    op.drop_column("diagnostic_attempts", "mastery_json")
    op.drop_column("diagnostic_attempts", "essay_score_percent")
    op.drop_column("diagnostic_attempts", "mcq_score_percent")
    op.drop_column("diagnostic_attempts", "attempt_id")
    op.drop_column("diagnostic_attempts", "assessment_id")
