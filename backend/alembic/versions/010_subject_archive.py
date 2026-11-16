"""Add inactive state for archived subjects.

Revision ID: 010_subject_archive
Revises: 009_normalize_numeric_student_register_numbers
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010_subject_archive"
down_revision: Union[str, None] = "009_normalize_numeric_student_register_numbers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subjects",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("subjects", "is_active")