"""Allow placement history to outlive a deleted Section.

Revision ID: 017_nullable_student_placement_section
Revises: 016_batch_student_placement
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "017_nullable_student_placement_section"
down_revision: Union[str, None] = "016_batch_student_placement"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("student_academic_placements") as batch_op:
        batch_op.alter_column(
            "section_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    detached_placements = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM student_academic_placements WHERE section_id IS NULL"
        )
    ).scalar_one()
    if detached_placements:
        raise RuntimeError(
            "Cannot require a Section for placement history while detached placements exist."
        )
    with op.batch_alter_table("student_academic_placements") as batch_op:
        batch_op.alter_column(
            "section_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
