"""Add one manual CO-PO mapping per subject.

Revision ID: 011_course_co_po_mapping
Revises: 010_subject_archive
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "011_course_co_po_mapping"
down_revision: Union[str, None] = "010_subject_archive"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "course_co_po_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("mapping_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subject_id", name="uq_course_co_po_mapping_subject"),
    )
    op.create_index(op.f("ix_course_co_po_mappings_id"), "course_co_po_mappings", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_course_co_po_mappings_id"), table_name="course_co_po_mappings")
    op.drop_table("course_co_po_mappings")