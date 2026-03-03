"""add demo user flag and email-role unique constraint

Revision ID: a1b2c3d4e5f8
Revises: d9e8f7a6b5c4
Create Date: 2026-03-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f8"
down_revision = "d9e8f7a6b5c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.execute(
        """
        WITH ranked AS (
          SELECT id,
                 ROW_NUMBER() OVER (PARTITION BY email ORDER BY id ASC) AS rn
          FROM users
        )
        UPDATE users u
        SET email = CONCAT(u.email, '+dup', u.id)
        FROM ranked r
        WHERE u.id = r.id AND r.rn > 1;
        """
    )

    # Drop the old plain index on email (created by index=True in the SQLAlchemy model).
    # This is a regular INDEX, not a unique constraint, so get_unique_constraints() misses it.
    op.execute("DROP INDEX IF EXISTS ix_users_email")

    # Also drop any legacy unique constraint on email-only (defensive, handles older DBs).
    bind = op.get_bind()
    insp = sa.inspect(bind)
    uniques = insp.get_unique_constraints("users")
    with op.batch_alter_table("users") as batch_op:
        for uq in uniques:
            cols = uq.get("column_names") or []
            if cols == ["email"] and uq.get("name"):
                batch_op.drop_constraint(uq["name"], type_="unique")
        # Only create if not already present (safe for re-runs).
        existing_uq_names = [uq.get("name") for uq in insp.get_unique_constraints("users")]
        if "uq_users_email_role" not in existing_uq_names:
            batch_op.create_unique_constraint("uq_users_email_role", ["email", "role"])


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("uq_users_email_role", type_="unique")
        batch_op.create_unique_constraint("users_email_key", ["email"])

    op.drop_column("users", "is_demo")
