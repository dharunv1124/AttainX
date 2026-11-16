"""Persist manual overall CO attainment inputs per subject.

Revision ID: 012_course_co_attainment_inputs
Revises: 011_course_co_po_mapping
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "012_course_co_attainment_inputs"
down_revision: Union[str, None] = "011_course_co_po_mapping"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "course_co_attainment_inputs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("input_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subject_id", name="uq_course_co_attainment_subject"),
    )
    op.create_index(op.f("ix_course_co_attainment_inputs_id"), "course_co_attainment_inputs", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_course_co_attainment_inputs_id"), table_name="course_co_attainment_inputs")
    op.drop_table("course_co_attainment_inputs")