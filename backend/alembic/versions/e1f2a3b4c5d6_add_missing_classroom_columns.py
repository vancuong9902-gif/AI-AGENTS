"""add missing classroom columns

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("classrooms")}

    if "description" not in cols:
        op.add_column("classrooms", sa.Column("description", sa.Text(), nullable=True))

    if "invite_code" not in cols:
        op.add_column("classrooms", sa.Column("invite_code", sa.String(32), nullable=True))

    if "course_id" not in cols:
        op.add_column("classrooms", sa.Column("course_id", sa.Integer(), nullable=True))

    if "is_active" not in cols:
        op.add_column(
            "classrooms",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("classrooms")}

    if "is_active" in cols:
        op.drop_column("classrooms", "is_active")

    if "course_id" in cols:
        op.drop_column("classrooms", "course_id")

    if "invite_code" in cols:
        op.drop_column("classrooms", "invite_code")

    if "description" in cols:
        op.drop_column("classrooms", "description")
