"""week11_learning_plan_homework_answer_json

Revision ID: f2c3d4e5f6a7
Revises: d1a2b3c4d5e6
Create Date: 2026-02-22

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "f2c3d4e5f6a7"
down_revision = "d1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    # Store structured answers for mixed homework (MCQ choices, etc.)
    op.add_column(
        "learning_plan_homework_submissions",
        sa.Column(
            "answer_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade():
    op.drop_column("learning_plan_homework_submissions", "answer_json")
