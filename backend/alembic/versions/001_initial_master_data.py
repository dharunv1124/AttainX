"""Initial Phase 4 master data and authentication tables

Revision ID: 001_initial_master_data
Revises: None
Create Date: 2026-09-24 06:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_master_data'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=50), nullable=False),
        sa.Column('email', sa.String(length=100), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=100), nullable=False),
        sa.Column('role', sa.String(length=30), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # 2. Departments table
    op.create_table(
        'departments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_departments_id'), 'departments', ['id'], unique=False)
    op.create_index(op.f('ix_departments_name'), 'departments', ['name'], unique=True)
    op.create_index(op.f('ix_departments_code'), 'departments', ['code'], unique=True)

    # 3. Years table (1st Year, 2nd Year, 3rd Year, 4th Year)
    op.create_table(
        'years',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('year_number', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('year_number'),
        sa.UniqueConstraint('name'),
    )
    op.create_index(op.f('ix_years_id'), 'years', ['id'], unique=False)

    # 4. Semesters table (1 to 8)
    op.create_table(
        'semesters',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('semester_number', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=20), nullable=False),
        sa.Column('year_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['year_id'], ['years.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('semester_number'),
        sa.UniqueConstraint('name'),
    )
    op.create_index(op.f('ix_semesters_id'), 'semesters', ['id'], unique=False)

    # 5. Sections table (Class within Department + Year + Semester)
    op.create_table(
        'sections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=20), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=False),
        sa.Column('year_id', sa.Integer(), nullable=False),
        sa.Column('semester_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['year_id'], ['years.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['semester_id'], ['semesters.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('department_id', 'year_id', 'semester_id', 'name', name='uq_dept_year_sem_section'),
    )
    op.create_index(op.f('ix_sections_id'), 'sections', ['id'], unique=False)
    op.create_index('idx_section_lookup', 'sections', ['department_id', 'year_id', 'semester_id'], unique=False)

    # 6. Students table (Belongs exclusively to section; independent of subject)
    op.create_table(
        'students',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('register_no', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('section_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['section_id'], ['sections.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_students_id'), 'students', ['id'], unique=False)
    op.create_index(op.f('ix_students_register_no'), 'students', ['register_no'], unique=True)
    op.create_index(op.f('ix_students_section_id'), 'students', ['section_id'], unique=False)

    # 7. Subjects table (Independent of students; Subject Name only)
    op.create_table(
        'subjects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_subjects_id'), 'subjects', ['id'], unique=False)
    op.create_index(op.f('ix_subjects_name'), 'subjects', ['name'], unique=True)


def downgrade() -> None:
    op.drop_table('subjects')
    op.drop_table('students')
    op.drop_table('sections')
    op.drop_table('semesters')
    op.drop_table('years')
    op.drop_table('departments')
    op.drop_table('users')
