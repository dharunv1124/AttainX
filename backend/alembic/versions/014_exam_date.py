"""Add an optional exam date to exams."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "014_exam_date"
down_revision: Union[str, None] = "013_saved_custom_exam_patterns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("exams", sa.Column("exam_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("exams", "exam_date")