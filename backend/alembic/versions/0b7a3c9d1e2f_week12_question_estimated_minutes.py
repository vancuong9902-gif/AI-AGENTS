"""week12_question_estimated_minutes

Revision ID: 0b7a3c9d1e2f
Revises: f2c3d4e5f6a7
Create Date: 2026-02-24

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0b7a3c9d1e2f"
down_revision = "f2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "questions",
        sa.Column(
            "estimated_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade():
    op.drop_column("questions", "estimated_minutes")
