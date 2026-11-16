"""Make Sections semester-independent and merge existing duplicate cohorts.

Revision ID: 004_section_by_department_year
Revises: 003_student_marks
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_section_by_department_year"
down_revision: Union[str, None] = "003_student_marks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _merge_duplicate_sections(bind) -> None:
    section_rows = bind.execute(sa.text(
        "SELECT id, department_id, year_id, name FROM sections ORDER BY id"
    )).mappings().all()
    student_counts = dict(bind.execute(sa.text(
        "SELECT section_id, COUNT(*) FROM students GROUP BY section_id"
    )).all())
    exam_counts = dict(bind.execute(sa.text(
        "SELECT section_id, COUNT(*) FROM exams GROUP BY section_id"
    )).all())

    groups = {}
    for row in section_rows:
        key = (row["department_id"], row["year_id"], row["name"].strip().upper())
        groups.setdefault(key, []).append(row)

    section_mapping = {}
    for key, rows in groups.items():
        canonical = max(
            rows,
            key=lambda row: (
                student_counts.get(row["id"], 0) + exam_counts.get(row["id"], 0),
                -row["id"],
            ),
        )
        for row in rows:
            section_mapping[row["id"]] = canonical["id"]

    exams = bind.execute(sa.text(
        "SELECT id, department_id, year_id, semester_id, section_id, subject_id, name FROM exams"
    )).mappings().all()
    exam_keys = set()
    for exam in exams:
        canonical_section_id = section_mapping.get(exam["section_id"], exam["section_id"])
        key = (
            exam["department_id"],
            exam["year_id"],
            exam["semester_id"],
            canonical_section_id,
            exam["subject_id"],
            exam["name"],
        )
        if key in exam_keys:
            raise RuntimeError(
                "Section merge would violate exam uniqueness; resolve duplicate exams before migration."
            )
        exam_keys.add(key)

    obsolete_ids = [section_id for section_id, canonical_id in section_mapping.items()
                    if section_id != canonical_id]
    for obsolete_id in obsolete_ids:
        canonical_id = section_mapping[obsolete_id]
        bind.execute(
            sa.text("UPDATE students SET section_id = :canonical_id WHERE section_id = :obsolete_id"),
            {"canonical_id": canonical_id, "obsolete_id": obsolete_id},
        )
        bind.execute(
            sa.text("UPDATE exams SET section_id = :canonical_id WHERE section_id = :obsolete_id"),
            {"canonical_id": canonical_id, "obsolete_id": obsolete_id},
        )

    for obsolete_id in obsolete_ids:
        bind.execute(
            sa.text("DELETE FROM sections WHERE id = :obsolete_id"),
            {"obsolete_id": obsolete_id},
        )

    for department_id, year_id, name in groups:
        canonical_id = next(
            section_mapping[row["id"]]
            for row in groups[(department_id, year_id, name)]
        )
        bind.execute(
            sa.text("UPDATE sections SET name = :name WHERE id = :section_id"),
            {"name": name, "section_id": canonical_id},
        )


def upgrade() -> None:
    bind = op.get_bind()
    _merge_duplicate_sections(bind)
    op.drop_index("idx_section_lookup", table_name="sections")

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(
            "sections",
            recreate="always",
            naming_convention={
                "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            },
        ) as batch_op:
            batch_op.drop_constraint("uq_dept_year_sem_section", type_="unique")
            batch_op.drop_constraint("fk_sections_semester_id_semesters", type_="foreignkey")
            batch_op.drop_column("semester_id")
            batch_op.create_unique_constraint(
                "uq_dept_year_section",
                ["department_id", "year_id", "name"],
            )
    elif bind.dialect.name == "postgresql":
        op.drop_constraint("uq_dept_year_sem_section", "sections", type_="unique")
        op.drop_constraint("sections_semester_id_fkey", "sections", type_="foreignkey")
        op.drop_column("sections", "semester_id")
        op.create_unique_constraint(
            "uq_dept_year_section",
            "sections",
            ["department_id", "year_id", "name"],
        )
    else:
        raise RuntimeError(f"Unsupported database dialect for Section migration: {bind.dialect.name}")

    op.create_index("idx_section_lookup", "sections", ["department_id", "year_id"], unique=False)


def downgrade() -> None:
    raise NotImplementedError(
        "Section cohort merging is irreversible because the original student-to-semester assignment is discarded."
    )