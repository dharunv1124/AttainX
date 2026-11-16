"""Format numeric CSE third-year A/B/C roll numbers as register numbers.

Revision ID: 009_normalize_numeric_student_register_numbers
Revises: 008_student_archive
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "009_normalize_numeric_student_register_numbers"
down_revision: Union[str, None] = "008_student_archive"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def register_number_for_roll(roll: int) -> str:
    cohort = 3 + (roll - 1) // 100
    cohort_roll = 1 + (roll - 1) % 100
    return f"24TD{cohort:02d}{cohort_roll:02d}"


def upgrade() -> None:
    bind = op.get_bind()
    section_ids = bind.execute(sa.text(
        """
        SELECT sections.id
        FROM sections
        JOIN departments ON departments.id = sections.department_id
        JOIN years ON years.id = sections.year_id
        WHERE upper(departments.code) = 'CSE'
          AND years.year_number = 3
          AND upper(trim(sections.name)) IN ('A', 'B', 'C')
        """
    )).scalars().all()

    for section_id in section_ids:
        students = bind.execute(
            sa.text("SELECT id, register_no FROM students WHERE section_id = :section_id"),
            {"section_id": section_id},
        ).mappings().all()
        for student in students:
            register_no = student["register_no"]
            if not register_no.isascii() or not register_no.isdecimal():
                continue
            roll = int(register_no)
            if roll < 1:
                continue
            bind.execute(
                sa.text("UPDATE students SET register_no = :register_no WHERE id = :student_id"),
                {
                    "register_no": register_number_for_roll(roll),
                    "student_id": student["id"],
                },
            )


def downgrade() -> None:
    raise NotImplementedError("Numeric roll-number conversion cannot be reversed safely.")