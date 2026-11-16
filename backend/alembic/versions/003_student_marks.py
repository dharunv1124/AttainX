"""Create student marks table for Phase 6 marks-entry workspace

Revision ID: 003_student_marks
Revises: 002_exam_configuration
Create Date: 2026-09-24 07:40:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '003_student_marks'
down_revision: Union[str, None] = '002_exam_configuration'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'student_marks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('exam_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('question_number', sa.String(length=20), nullable=False),
        sa.Column('obtained_mark', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('exam_id', 'student_id', 'question_number', name='uq_exam_student_question_mark'),
    )
    op.create_index(op.f('ix_student_marks_id'), 'student_marks', ['id'], unique=False)
    op.create_index(op.f('ix_student_marks_exam_id'), 'student_marks', ['exam_id'], unique=False)
    op.create_index(op.f('ix_student_marks_student_id'), 'student_marks', ['student_id'], unique=False)
    op.create_index('idx_student_mark_lookup', 'student_marks', ['exam_id', 'student_id'], unique=False)


def downgrade() -> None:
    op.drop_table('student_marks')
