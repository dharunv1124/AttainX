"""Create exam configuration tables: exams, exam_covered_cos, exam_questions

Revision ID: 002_exam_configuration
Revises: 001_initial_master_data
Create Date: 2026-09-24 06:40:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '002_exam_configuration'
down_revision: Union[str, None] = '001_initial_master_data'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. exams table
    op.create_table(
        'exams',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('exam_type', sa.String(length=50), nullable=False, server_default='CUSTOM'),
        sa.Column('department_id', sa.Integer(), nullable=False),
        sa.Column('year_id', sa.Integer(), nullable=False),
        sa.Column('semester_id', sa.Integer(), nullable=False),
        sa.Column('section_id', sa.Integer(), nullable=False),
        sa.Column('subject_id', sa.Integer(), nullable=False),
        sa.Column('pass_percentage', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['year_id'], ['years.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['semester_id'], ['semesters.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['section_id'], ['sections.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_exams_id'), 'exams', ['id'], unique=False)
    op.create_index('idx_exam_class_subject', 'exams', ['department_id', 'year_id', 'semester_id', 'section_id', 'subject_id'], unique=False)

    # 2. exam_covered_cos table
    op.create_table(
        'exam_covered_cos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('exam_id', sa.Integer(), nullable=False),
        sa.Column('co_code', sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('exam_id', 'co_code', name='uq_exam_covered_co'),
    )
    op.create_index(op.f('ix_exam_covered_cos_id'), 'exam_covered_cos', ['id'], unique=False)
    op.create_index(op.f('ix_exam_covered_cos_exam_id'), 'exam_covered_cos', ['exam_id'], unique=False)

    # 3. exam_questions table
    op.create_table(
        'exam_questions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('exam_id', sa.Integer(), nullable=False),
        sa.Column('question_number', sa.String(length=20), nullable=False),
        sa.Column('max_marks', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('co_code', sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('exam_id', 'question_number', name='uq_exam_question_number'),
    )
    op.create_index(op.f('ix_exam_questions_id'), 'exam_questions', ['id'], unique=False)
    op.create_index(op.f('ix_exam_questions_exam_id'), 'exam_questions', ['exam_id'], unique=False)


def downgrade() -> None:
    op.drop_table('exam_questions')
    op.drop_table('exam_covered_cos')
    op.drop_table('exams')
