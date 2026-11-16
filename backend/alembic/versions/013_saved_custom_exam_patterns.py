"""Store reusable grouped custom exam patterns independently of exams."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "013_saved_custom_exam_patterns"
down_revision: Union[str, None] = "012_course_co_attainment_inputs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saved_custom_exam_patterns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("groups", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_saved_custom_exam_patterns_id", "saved_custom_exam_patterns", ["id"], unique=False)
    op.create_index("ix_saved_custom_exam_patterns_name", "saved_custom_exam_patterns", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_saved_custom_exam_patterns_name", table_name="saved_custom_exam_patterns")
    op.drop_index("ix_saved_custom_exam_patterns_id", table_name="saved_custom_exam_patterns")
    op.drop_table("saved_custom_exam_patterns")