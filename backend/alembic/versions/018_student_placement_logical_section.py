"""Preserve logical Section identity on student placements.

Revision ID: 018_student_placement_logical_section
Revises: 017_nullable_student_placement_section
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "018_student_placement_logical_section"
down_revision: Union[str, None] = "017_nullable_student_placement_section"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column(
        "student_academic_placements",
        sa.Column("section_name", sa.String(length=20), nullable=True),
    )
    bind.execute(
        sa.text(
            """
            UPDATE student_academic_placements
            SET section_name = (
                SELECT sections.name
                FROM sections
                WHERE sections.id = student_academic_placements.section_id
            )
            WHERE section_id IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_column("student_academic_placements", "section_name")
