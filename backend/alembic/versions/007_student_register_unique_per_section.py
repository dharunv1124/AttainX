"""Scope student register-number uniqueness to each section.

Revision ID: 007_student_register_unique_per_section
Revises: 006_correct_cse_year3_semester6_subjects
"""
from typing import Sequence, Union

from alembic import op

revision: str = "007_student_register_unique_per_section"
down_revision: Union[str, None] = "006_correct_cse_year3_semester6_subjects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.drop_index("ix_students_register_no", table_name="students")
    op.create_index("ix_students_register_no", "students", ["register_no"], unique=False)
    op.create_index(
        "uq_student_section_register_no",
        "students",
        ["section_id", "register_no"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_student_section_register_no", table_name="students")
    op.drop_index("ix_students_register_no", table_name="students")
    op.create_index("ix_students_register_no", "students", ["register_no"], unique=True)