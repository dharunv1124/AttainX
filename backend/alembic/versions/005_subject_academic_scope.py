"""Scope Subjects by Department, Year, and Semester.

Revision ID: 005_subject_academic_scope
Revises: 004_section_by_department_year
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005_subject_academic_scope"
down_revision: Union[str, None] = "004_section_by_department_year"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CURRICULUM = {
    5: (
        "DATABASE SYSTEM",
        "COMPUTER NETWORKS",
        "OPERATING SYSTEM",
        "THEORY OF COMPUTATION",
        "SOFTWARE ENGINEERING",
    ),
    6: (
        "WEB TECHNOLOGIES",
        "COMPILER DESIGN",
        "DISTRIBUTED COMPUTING SYSTEM",
        "ARTIFICIAL INTELLIGENCE AND MACHINE LEARNING",
    ),
}


DEPARTMENTS = (
    ("Computer Science and Engineering", "CSE"),
    ("Information Technology", "IT"),
    ("Electronics and Communication Engineering", "ECE"),
    ("Artificial Intelligence and Machine Learning", "AIML"),
    ("Internet of Things", "IOT"),
    ("Electrical and Electronics Engineering", "EEE"),
    ("Robotics and Automation", "RA"),
    ("Mechanical Engineering", "MECH"),
    ("Food Technology", "FT"),
)
YEAR_NAMES = {
    1: "1st Year",
    2: "2nd Year",
    3: "3rd Year",
    4: "4th Year",
}
SEMESTER_YEARS = {
    1: 1,
    2: 1,
    3: 2,
    4: 2,
    5: 3,
    6: 3,
    7: 4,
    8: 4,
}


def _ensure_academic_reference_data(bind) -> None:
    departments = bind.execute(
        sa.text("SELECT id, name, code FROM departments")
    ).mappings().all()
    for expected_name, expected_code in DEPARTMENTS:
        code_matches = [
            row for row in departments
            if row["code"].strip().upper() == expected_code
        ]
        name_matches = [
            row for row in departments
            if row["name"].strip().casefold() == expected_name.casefold()
        ]
        matches = {row["id"]: row for row in code_matches + name_matches}
        if matches:
            if len(matches) != 1:
                raise RuntimeError(
                    f"Conflicting department mapping for {expected_code} ({expected_name})."
                )
            existing = next(iter(matches.values()))
            if (
                existing["code"].strip().upper() != expected_code
                or existing["name"].strip().casefold() != expected_name.casefold()
            ):
                raise RuntimeError(
                    f"Conflicting department mapping for {expected_code} ({expected_name})."
                )
            continue

        bind.execute(
            sa.text("INSERT INTO departments (name, code) VALUES (:name, :code)"),
            {"name": expected_name, "code": expected_code},
        )

    years = bind.execute(
        sa.text("SELECT id, year_number, name FROM years")
    ).mappings().all()
    year_ids = {}
    for number, name in YEAR_NAMES.items():
        number_matches = [row for row in years if row["year_number"] == number]
        name_matches = [
            row for row in years
            if row["name"].strip().casefold() == name.casefold()
        ]
        matches = {row["id"]: row for row in number_matches + name_matches}
        if matches:
            if len(matches) != 1:
                raise RuntimeError(f"Conflicting academic year mapping for {name}.")
            existing = next(iter(matches.values()))
            if (
                existing["year_number"] != number
                or existing["name"].strip().casefold() != name.casefold()
            ):
                raise RuntimeError(f"Conflicting academic year mapping for {name}.")
            year_ids[number] = existing["id"]
            continue

        bind.execute(
            sa.text("INSERT INTO years (year_number, name) VALUES (:number, :name)"),
            {"number": number, "name": name},
        )
        year_ids[number] = bind.execute(
            sa.text("SELECT id FROM years WHERE year_number = :number"),
            {"number": number},
        ).scalar_one()

    semesters = bind.execute(
        sa.text("SELECT id, semester_number, name, year_id FROM semesters")
    ).mappings().all()
    for number, year_number in SEMESTER_YEARS.items():
        name = f"Semester {number}"
        number_matches = [
            row for row in semesters if row["semester_number"] == number
        ]
        name_matches = [
            row for row in semesters
            if row["name"].strip().casefold() == name.casefold()
        ]
        matches = {row["id"]: row for row in number_matches + name_matches}
        if matches:
            if len(matches) != 1:
                raise RuntimeError(f"Conflicting academic semester mapping for {name}.")
            existing = next(iter(matches.values()))
            if (
                existing["semester_number"] != number
                or existing["name"].strip().casefold() != name.casefold()
                or existing["year_id"] != year_ids[year_number]
            ):
                raise RuntimeError(f"Conflicting academic semester mapping for {name}.")
            continue

        bind.execute(
            sa.text(
                "INSERT INTO semesters (semester_number, name, year_id) "
                "VALUES (:number, :name, :year_id)"
            ),
            {"number": number, "name": name, "year_id": year_ids[year_number]},
        )


def _academic_contexts(bind):
    department_id = bind.execute(sa.text(
        "SELECT id FROM departments WHERE code = 'CSE'"
    )).scalar_one_or_none()
    year_id = bind.execute(sa.text(
        "SELECT id FROM years WHERE year_number = 3"
    )).scalar_one_or_none()
    if department_id is None or year_id is None:
        raise RuntimeError("CSE and 3rd Year are required before Subject curriculum migration.")

    semesters = {}
    for semester_number in CURRICULUM:
        semester_id = bind.execute(
            sa.text("SELECT id FROM semesters WHERE semester_number = :number AND year_id = :year_id"),
            {"number": semester_number, "year_id": year_id},
        ).scalar_one_or_none()
        if semester_id is None:
            raise RuntimeError(f"Semester {semester_number} for 3rd Year is required.")
        semesters[semester_number] = semester_id

    return department_id, year_id, semesters


def _scope_existing_subjects(bind, department_id, year_id, semesters) -> None:
    subjects = sa.table(
        "subjects",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("department_id", sa.Integer),
        sa.column("year_id", sa.Integer),
        sa.column("semester_id", sa.Integer),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    exam_rows = bind.execute(sa.text(
        "SELECT id, subject_id, department_id, year_id, semester_id FROM exams ORDER BY id"
    )).mappings().all()
    exams_by_subject = {}
    for exam in exam_rows:
        context = (exam["department_id"], exam["year_id"], exam["semester_id"])
        exams_by_subject.setdefault(exam["subject_id"], {}).setdefault(context, []).append(exam["id"])

    known_curriculum = {
        name: (department_id, year_id, semesters[semester_number])
        for semester_number, names in CURRICULUM.items()
        for name in names
    }
    legacy_subjects = bind.execute(sa.text(
        "SELECT id, name FROM subjects ORDER BY id"
    )).mappings().all()

    for subject in legacy_subjects:
        contexts = exams_by_subject.get(subject["id"], {})
        normalized_name = subject["name"].strip().upper()
        if contexts:
            primary_context = min(
                contexts,
                key=lambda context: (-len(contexts[context]), context),
            )
            invalid_contexts = [
                context
                for context in contexts
                if bind.execute(
                    sa.text("SELECT year_id FROM semesters WHERE id = :semester_id"),
                    {"semester_id": context[2]},
                ).scalar_one_or_none() != context[1]
            ]
            if invalid_contexts:
                print(
                    f"Leaving legacy Subject {subject['id']} ({subject['name']!r}) unscoped: "
                    "an Exam references an inconsistent Year/Semester context."
                )
                continue

            bind.execute(
                sa.update(subjects)
                .where(subjects.c.id == subject["id"])
                .values(
                    department_id=primary_context[0],
                    year_id=primary_context[1],
                    semester_id=primary_context[2],
                )
            )

            for context, exam_ids in contexts.items():
                if context == primary_context:
                    continue
                duplicate_id = bind.execute(
                    sa.insert(subjects)
                    .values(
                        name=subject["name"],
                        department_id=context[0],
                        year_id=context[1],
                        semester_id=context[2],
                        created_at=sa.func.now(),
                        updated_at=sa.func.now(),
                    )
                    .returning(subjects.c.id)
                ).scalar_one()
                bind.execute(
                    sa.text("UPDATE exams SET subject_id = :new_id WHERE id IN :exam_ids")
                    .bindparams(sa.bindparam("exam_ids", expanding=True)),
                    {"new_id": duplicate_id, "exam_ids": exam_ids},
                )
            continue

        scope = known_curriculum.get(normalized_name)
        if scope is None:
            print(
                f"Leaving legacy Subject {subject['id']} ({subject['name']!r}) unscoped: "
                "no Exam context or confirmed curriculum mapping exists."
            )
            continue

        bind.execute(
            sa.update(subjects)
            .where(subjects.c.id == subject["id"])
            .values(department_id=scope[0], year_id=scope[1], semester_id=scope[2])
        )


def _ensure_curriculum_subjects(bind, department_id, year_id, semesters) -> None:
    subjects = sa.table(
        "subjects",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("department_id", sa.Integer),
        sa.column("year_id", sa.Integer),
        sa.column("semester_id", sa.Integer),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    for semester_number, names in CURRICULUM.items():
        for name in names:
            exists = bind.execute(
                sa.select(subjects.c.id).where(
                    subjects.c.department_id == department_id,
                    subjects.c.year_id == year_id,
                    subjects.c.semester_id == semesters[semester_number],
                    sa.func.upper(sa.func.trim(subjects.c.name)) == name,
                )
            ).first()
            if exists:
                continue
            bind.execute(
                sa.insert(subjects).values(
                    name=name,
                    department_id=department_id,
                    year_id=year_id,
                    semester_id=semesters[semester_number],
                    created_at=sa.func.now(),
                    updated_at=sa.func.now(),
                )
            )


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_academic_reference_data(bind)
    department_id, year_id, semesters = _academic_contexts(bind)
    op.drop_index("ix_subjects_name", table_name="subjects")

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("subjects", recreate="always") as batch_op:
            batch_op.add_column(sa.Column("department_id", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("year_id", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("semester_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_subjects_department_id_departments",
                "departments",
                ["department_id"],
                ["id"],
                ondelete="RESTRICT",
            )
            batch_op.create_foreign_key(
                "fk_subjects_year_id_years",
                "years",
                ["year_id"],
                ["id"],
                ondelete="RESTRICT",
            )
            batch_op.create_foreign_key(
                "fk_subjects_semester_id_semesters",
                "semesters",
                ["semester_id"],
                ["id"],
                ondelete="RESTRICT",
            )
            batch_op.create_check_constraint(
                "ck_subject_scope_all_or_none",
                "(department_id IS NULL AND year_id IS NULL AND semester_id IS NULL) "
                "OR (department_id IS NOT NULL AND year_id IS NOT NULL AND semester_id IS NOT NULL)",
            )
            batch_op.create_unique_constraint(
                "uq_subject_department_year_semester_name",
                ["department_id", "year_id", "semester_id", "name"],
            )
    elif bind.dialect.name == "postgresql":
        for column_name in ("department_id", "year_id", "semester_id"):
            op.add_column("subjects", sa.Column(column_name, sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_subjects_department_id_departments", "subjects", "departments",
            ["department_id"], ["id"], ondelete="RESTRICT",
        )
        op.create_foreign_key(
            "fk_subjects_year_id_years", "subjects", "years",
            ["year_id"], ["id"], ondelete="RESTRICT",
        )
        op.create_foreign_key(
            "fk_subjects_semester_id_semesters", "subjects", "semesters",
            ["semester_id"], ["id"], ondelete="RESTRICT",
        )
        op.create_check_constraint(
            "ck_subject_scope_all_or_none",
            "subjects",
            "(department_id IS NULL AND year_id IS NULL AND semester_id IS NULL) "
            "OR (department_id IS NOT NULL AND year_id IS NOT NULL AND semester_id IS NOT NULL)",
        )
        op.create_unique_constraint(
            "uq_subject_department_year_semester_name",
            "subjects",
            ["department_id", "year_id", "semester_id", "name"],
        )
    else:
        raise RuntimeError(f"Unsupported database dialect for Subject migration: {bind.dialect.name}")

    op.create_index("ix_subjects_name", "subjects", ["name"], unique=False)
    _scope_existing_subjects(bind, department_id, year_id, semesters)
    _ensure_curriculum_subjects(bind, department_id, year_id, semesters)


def downgrade() -> None:
    raise NotImplementedError(
        "Subject scoping and context-specific copies cannot be safely merged back into global Subjects."
    )