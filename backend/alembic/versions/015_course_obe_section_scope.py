"""Scope Course OBE persistence by subject and section.

Existing subject-only rows are retained with section_id NULL and are not
assigned to any section automatically.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "015_course_obe_section_scope"
down_revision: Union[str, None] = "014_exam_date"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("course_co_po_mappings", recreate="always") as batch_op:
        batch_op.drop_constraint("uq_course_co_po_mapping_subject", type_="unique")
        batch_op.add_column(sa.Column("section_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_course_co_po_mappings_section_id_sections",
            "sections",
            ["section_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            "uq_course_co_po_mapping_subject_section",
            ["subject_id", "section_id"],
        )

    with op.batch_alter_table("course_co_attainment_inputs", recreate="always") as batch_op:
        batch_op.drop_constraint("uq_course_co_attainment_subject", type_="unique")
        batch_op.add_column(sa.Column("section_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_course_co_attainment_inputs_section_id_sections",
            "sections",
            ["section_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            "uq_course_co_attainment_subject_section",
            ["subject_id", "section_id"],
        )


def downgrade() -> None:
    raise RuntimeError(
        "This migration preserves section-specific rows and cannot be safely downgraded."
    )