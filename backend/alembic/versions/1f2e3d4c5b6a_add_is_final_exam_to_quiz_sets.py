"""add is_final_exam to quiz_sets

Revision ID: 1f2e3d4c5b6a
Revises: e3f4a5b6c7d8
Create Date: 2026-02-28 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1f2e3d4c5b6a"
down_revision: Union[str, Sequence[str], None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quiz_sets",
        sa.Column("is_final_exam", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("quiz_sets", "is_final_exam")
