"""Remove two incorrect subjects from CSE third-year Semester 6 scope.

Revision ID: 006_correct_cse_year3_semester6_subjects
Revises: 005_subject_academic_scope
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006_correct_cse_year3_semester6_subjects"
down_revision: Union[str, None] = "005_subject_academic_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


INCORRECT_SEMESTER_6_SUBJECTS = (
    "DATABASE MANAGEMENT SYSTEMS",
    "THEORY OF COMPUTATION",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=sa.String(length=32),
            type_=sa.String(length=255),
            existing_nullable=False,
        )

    bind.execute(
        sa.text(
            """
            UPDATE subjects
            SET department_id = NULL, year_id = NULL, semester_id = NULL
            WHERE department_id = (SELECT id FROM departments WHERE code = 'CSE')
              AND year_id = (SELECT id FROM years WHERE year_number = 3)
              AND semester_id = (SELECT id FROM semesters WHERE semester_number = 6)
              AND upper(trim(name)) IN (:database_management_systems, :theory_of_computation)
            """
        ),
        {
            "database_management_systems": INCORRECT_SEMESTER_6_SUBJECTS[0],
            "theory_of_computation": INCORRECT_SEMESTER_6_SUBJECTS[1],
        },
    )


def downgrade() -> None:
    raise NotImplementedError("The previous subject scopes cannot be restored safely.")