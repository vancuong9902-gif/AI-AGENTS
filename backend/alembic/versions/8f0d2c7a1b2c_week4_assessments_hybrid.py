"""week4 assessments hybrid (mcq + essay)

Revision ID: 8f0d2c7a1b2c
Revises: 6b6e9c8e4d7a
Create Date: 2026-01-28

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "8f0d2c7a1b2c"
down_revision = "6b6e9c8e4d7a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # quiz_sets.kind
    op.add_column(
        "quiz_sets",
        sa.Column("kind", sa.String(length=50), nullable=False, server_default=sa.text("'quiz'")),
    )
    op.create_index(op.f("ix_quiz_sets_kind"), "quiz_sets", ["kind"], unique=False)

    # questions: rubric + max_points for essay
    op.add_column(
        "questions",
        sa.Column(
            "max_points",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "questions",
        sa.Column(
            "rubric",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("questions", "rubric")
    op.drop_column("questions", "max_points")

    op.drop_index(op.f("ix_quiz_sets_kind"), table_name="quiz_sets")
    op.drop_column("quiz_sets", "kind")
