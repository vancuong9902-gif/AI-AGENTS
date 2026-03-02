"""merge_heads

Revision ID: c0eed4ba67ff
Revises: 3b4c5d6e7f8a, a1b2c3d4e5f7, a9b8c7d6e5f4, a9b8c7d6e5f5, c7d8e9f0a1b2, e3f4a5b6c7d9, f0e1d2c3b4a5
Create Date: 2026-03-02 09:00:00.834668

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c0eed4ba67ff'
down_revision: Union[str, Sequence[str], None] = ('3b4c5d6e7f8a', 'a1b2c3d4e5f7', 'a9b8c7d6e5f4', 'a9b8c7d6e5f5', 'c7d8e9f0a1b2', 'e3f4a5b6c7d9', 'f0e1d2c3b4a5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
