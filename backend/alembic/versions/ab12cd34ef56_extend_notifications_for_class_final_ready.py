"""extend notifications for class final ready

Revision ID: ab12cd34ef56
Revises: aa12bb34cc56
Create Date: 2026-03-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "ab12cd34ef56"
down_revision = "aa12bb34cc56"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        batch.add_column(sa.Column("teacher_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("student_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("quiz_id", sa.Integer(), nullable=True))

        batch.create_foreign_key("fk_notifications_teacher_id", "users", ["teacher_id"], ["id"])
        batch.create_foreign_key("fk_notifications_student_id", "users", ["student_id"], ["id"])
        batch.create_foreign_key("fk_notifications_quiz_id", "quiz_sets", ["quiz_id"], ["id"])

        batch.create_index("ix_notifications_teacher_id", ["teacher_id"], unique=False)
        batch.create_index("ix_notifications_student_id", ["student_id"], unique=False)
        batch.create_index("ix_notifications_quiz_id", ["quiz_id"], unique=False)

    op.execute("UPDATE notifications SET payload_json = COALESCE(data, '{}'::jsonb) WHERE payload_json IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("notifications") as batch:
        batch.drop_index("ix_notifications_quiz_id")
        batch.drop_index("ix_notifications_student_id")
        batch.drop_index("ix_notifications_teacher_id")

        batch.drop_constraint("fk_notifications_quiz_id", type_="foreignkey")
        batch.drop_constraint("fk_notifications_student_id", type_="foreignkey")
        batch.drop_constraint("fk_notifications_teacher_id", type_="foreignkey")

        batch.drop_column("quiz_id")
        batch.drop_column("student_id")
        batch.drop_column("teacher_id")
        batch.drop_column("payload_json")
