"""merge heads after fixing duplicate revision id

Revision ID: d0e1f2a3b4c5
Revises: a1b2c3d4e5f8, b2c3d4e5f6a8
Create Date: 2026-03-03 00:10:00.000000
"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = ("a1b2c3d4e5f8", "b2c3d4e5f6a8")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
