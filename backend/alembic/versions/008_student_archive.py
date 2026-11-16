"""Add reversible student archiving and active-only register uniqueness.

Revision ID: 008_student_archive
Revises: 007_student_register_unique_per_section
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008_student_archive"
down_revision: Union[str, None] = "007_student_register_unique_per_section"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("students", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_index("uq_student_section_register_no", table_name="students")
    op.create_index(
        "uq_student_section_register_no_active",
        "students",
        ["section_id", "register_no"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
        sqlite_where=sa.text("archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_student_section_register_no_active", table_name="students")
    op.drop_column("students", "archived_at")
    op.create_index(
        "uq_student_section_register_no",
        "students",
        ["section_id", "register_no"],
        unique=True,
    )