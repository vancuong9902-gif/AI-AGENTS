"""week6 question bloom level

Revision ID: d4a1f2c7e8b9
Revises: c2d9b0a2b5ef
Create Date: 2026-01-31

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d4a1f2c7e8b9"
down_revision = "c2d9b0a2b5ef"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "questions",
        sa.Column(
            "bloom_level",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'understand'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("questions", "bloom_level")
