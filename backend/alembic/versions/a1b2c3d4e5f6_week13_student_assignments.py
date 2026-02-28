"""week13 student assignments

Revision ID: a1b2c3d4e5f6
Revises: 0b7a3c9d1e2f
Create Date: 2026-02-28

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "0b7a3c9d1e2f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("classroom_id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("assignment_type", sa.String(length=32), nullable=False),
        sa.Column("student_level", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("content_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["classroom_id"], ["classrooms.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["topic_id"], ["document_topics.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_student_assignments_student_id", "student_assignments", ["student_id"])
    op.create_index("ix_student_assignments_classroom_id", "student_assignments", ["classroom_id"])
    op.create_index("ix_student_assignments_document_id", "student_assignments", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_student_assignments_document_id", table_name="student_assignments")
    op.drop_index("ix_student_assignments_classroom_id", table_name="student_assignments")
    op.drop_index("ix_student_assignments_student_id", table_name="student_assignments")
    op.drop_table("student_assignments")
