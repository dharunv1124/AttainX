"""Add batch-scoped student identities and academic placement history.

Revision ID: 016_batch_student_placement
Revises: 015_course_obe_section_scope
"""
import os
import sqlite3
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "016_batch_student_placement"
down_revision: Union[str, None] = "015_course_obe_section_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _preflight(bind) -> None:
    inspector = sa.inspect(bind)
    if "batches" in inspector.get_table_names():
        raise RuntimeError(
            "A batches table already exists at revision 015; inspect the partial schema before continuing."
        )

    duplicate_contexts = (
        (
            "sections",
            """
            SELECT department_id, year_id, name, COUNT(*) AS record_count
            FROM sections GROUP BY department_id, year_id, name HAVING COUNT(*) > 1
            """,
        ),
        (
            "subjects",
            """
            SELECT department_id, year_id, semester_id, name, COUNT(*) AS record_count
            FROM subjects
            WHERE department_id IS NOT NULL AND year_id IS NOT NULL AND semester_id IS NOT NULL
            GROUP BY department_id, year_id, semester_id, name
            HAVING COUNT(*) > 1
            """,
        ),
        (
            "exams",
            """
            SELECT department_id, year_id, semester_id, section_id, subject_id,
                   name, COUNT(*) AS record_count
            FROM exams
            GROUP BY department_id, year_id, semester_id, section_id, subject_id, name
            HAVING COUNT(*) > 1
            """,
        ),
    )
    for table_name, query in duplicate_contexts:
        duplicates = bind.execute(sa.text(query)).all()
        if duplicates:
            raise RuntimeError(
                f"Cannot apply Batch uniqueness constraints: existing duplicate {table_name} contexts were found. "
                "Resolve them without deleting historical marks or OBE data, then retry."
            )

    invalid_students = bind.execute(sa.text(
        """
        SELECT students.id
        FROM students
        LEFT JOIN sections ON sections.id = students.section_id
        LEFT JOIN years ON years.id = sections.year_id
        WHERE sections.id IS NULL OR years.id IS NULL
        LIMIT 10
        """
    )).scalars().all()
    if invalid_students:
        raise RuntimeError(
            "Cannot backfill student placement because students have missing Section/Year references: "
            + ", ".join(str(student_id) for student_id in invalid_students)
        )

    invalid_exams = bind.execute(sa.text(
        """
        SELECT exams.id
        FROM exams
        LEFT JOIN sections ON sections.id = exams.section_id
        WHERE sections.id IS NULL
           OR sections.department_id != exams.department_id
           OR sections.year_id != exams.year_id
        LIMIT 10
        """
    )).scalars().all()
    if invalid_exams:
        raise RuntimeError(
            "Cannot assign exam batches when exam and section contexts disagree: "
            + ", ".join(str(exam_id) for exam_id in invalid_exams)
        )

def _verify_sqlite_backup(bind) -> None:
    if bind.dialect.name != "sqlite":
        return
    backup_value = os.environ.get("OBE_DB_BACKUP_PATH")
    if not backup_value:
        raise RuntimeError(
            "SQLite Batch migration requires OBE_DB_BACKUP_PATH to point to a verified backup "
            "created before migration."
        )
    backup_path = Path(backup_value).expanduser().resolve()
    source_path = Path(bind.exec_driver_sql("PRAGMA database_list").first()[2]).resolve()
    if not backup_path.is_file() or backup_path == source_path:
        raise RuntimeError("OBE_DB_BACKUP_PATH must be an existing file separate from the source database.")
    try:
        with sqlite3.connect(backup_path.as_uri() + "?mode=ro", uri=True) as backup_db:
            integrity = backup_db.execute("PRAGMA integrity_check").fetchone()
            backup_revision = backup_db.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()
            with sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True) as source_db:
                source_tables = source_db.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                ).fetchall()
                backup_tables = backup_db.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                ).fetchall()
                if source_tables != backup_tables:
                    raise RuntimeError("SQLite backup tables do not match the source database.")
                for (table_name,) in source_tables:
                    escaped_name = table_name.replace('"', '""')
                    primary_key = sorted(
                        (
                            (row[5], row[1])
                            for row in source_db.execute(f'PRAGMA table_info("{escaped_name}")')
                            if row[5]
                        )
                    )
                    ordering = ", ".join(f'"{column}"' for _, column in primary_key) or "rowid"
                    source_rows = source_db.execute(
                        f'SELECT * FROM "{escaped_name}" ORDER BY {ordering}'
                    ).fetchall()
                    backup_rows = backup_db.execute(
                        f'SELECT * FROM "{escaped_name}" ORDER BY {ordering}'
                    ).fetchall()
                    if source_rows != backup_rows:
                        raise RuntimeError(
                            f"SQLite backup does not match current source table {table_name!r}."
                        )
    except sqlite3.DatabaseError as error:
        raise RuntimeError(f"SQLite backup could not be verified: {error}") from error
    if integrity is None or integrity[0] != "ok":
        raise RuntimeError(f"SQLite backup integrity check failed: {integrity}")
    source_revision = bind.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    if backup_revision is None or backup_revision[0] != source_revision:
        raise RuntimeError("SQLite backup Alembic revision does not match the migration source database.")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in ("sqlite", "postgresql"):
        raise RuntimeError(f"Unsupported database dialect for Batch migration: {bind.dialect.name}")

    if bind.dialect.name == "sqlite":
        bind.exec_driver_sql("BEGIN IMMEDIATE")
    _verify_sqlite_backup(bind)
    _preflight(bind)

    op.create_table(
        "batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_name", sa.String(length=50), nullable=False, unique=True),
        sa.Column("start_year", sa.Integer(), nullable=False),
        sa.Column("end_year", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("start_year", "end_year", name="uq_batch_year_range"),
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO batches (batch_name, start_year, end_year, is_active, created_at, updated_at)
            VALUES ('2024–28', 2024, 2028, :is_active, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        ).bindparams(sa.bindparam("is_active", type_=sa.Boolean())),
        {"is_active": True},
    )
    default_batch_id = bind.execute(sa.text(
        "SELECT id FROM batches WHERE start_year = 2024 AND end_year = 2028"
    )).scalar_one()

    op.drop_index("idx_section_lookup", table_name="sections")
    op.drop_index("uq_student_section_register_no_active", table_name="students")
    for table_name in ("sections", "subjects", "exams", "students"):
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            batch_op.add_column(sa.Column("batch_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                f"fk_{table_name}_batch_id_batches",
                "batches",
                ["batch_id"],
                ["id"],
                ondelete="RESTRICT",
            )

    bind.execute(sa.text("UPDATE sections SET batch_id = :batch_id"), {"batch_id": default_batch_id})
    bind.execute(sa.text("UPDATE subjects SET batch_id = :batch_id"), {"batch_id": default_batch_id})
    bind.execute(sa.text(
        """
        UPDATE subjects
        SET department_id = (
                SELECT MIN(exams.department_id) FROM exams WHERE exams.subject_id = subjects.id
            ),
            year_id = (
                SELECT MIN(exams.year_id) FROM exams WHERE exams.subject_id = subjects.id
            ),
            semester_id = (
                SELECT MIN(exams.semester_id) FROM exams WHERE exams.subject_id = subjects.id
            )
        WHERE subjects.department_id IS NULL
          AND (
              SELECT COUNT(DISTINCT exams.department_id)
              FROM exams WHERE exams.subject_id = subjects.id
          ) = 1
          AND (
              SELECT COUNT(DISTINCT exams.year_id)
              FROM exams WHERE exams.subject_id = subjects.id
          ) = 1
          AND (
              SELECT COUNT(DISTINCT exams.semester_id)
              FROM exams WHERE exams.subject_id = subjects.id
          ) = 1
        """
    ))
    bind.execute(sa.text(
        """
        UPDATE exams
        SET batch_id = (
            SELECT sections.batch_id FROM sections WHERE sections.id = exams.section_id
        )
        """
    ))
    bind.execute(sa.text(
        """
        UPDATE students
        SET batch_id = (
            SELECT sections.batch_id FROM sections WHERE sections.id = students.section_id
        )
        """
    ))
    duplicate_subjects = bind.execute(sa.text(
        """
        SELECT department_id, year_id, semester_id, name, COUNT(*) AS record_count
        FROM subjects
        WHERE department_id IS NOT NULL AND year_id IS NOT NULL AND semester_id IS NOT NULL
        GROUP BY department_id, year_id, semester_id, name
        HAVING COUNT(*) > 1
        """
    )).all()
    if duplicate_subjects:
        raise RuntimeError(
            "Batch migration inferred duplicate Subject contexts from existing Exams. "
            "Resolve the subject references without deleting historical records, then retry."
        )

    op.create_table(
        "student_academic_placements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("year_id", sa.Integer(), nullable=False),
        sa.Column("semester_id", sa.Integer(), nullable=True),
        sa.Column("section_id", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["year_id"], ["years.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["semester_id"], ["semesters.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["section_id"], ["sections.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_student_placement_effective_dates",
        ),
    )
    op.create_index("ix_student_academic_placements_student_id", "student_academic_placements", ["student_id"])
    op.create_index("ix_student_academic_placements_batch_id", "student_academic_placements", ["batch_id"])
    op.create_index("ix_student_academic_placements_section_id", "student_academic_placements", ["section_id"])
    op.create_index(
        "uq_student_current_academic_placement",
        "student_academic_placements",
        ["student_id"],
        unique=True,
        sqlite_where=sa.text("is_current = 1"),
        postgresql_where=sa.text("is_current"),
    )
    op.create_index(
        "idx_placement_section_current",
        "student_academic_placements",
        ["section_id", "is_current"],
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO student_academic_placements (
                student_id, batch_id, department_id, year_id, semester_id, section_id,
                is_current, effective_from, effective_to, created_at
            )
            SELECT students.id, students.batch_id, sections.department_id, sections.year_id,
                   NULL,
                   sections.id, :is_current, COALESCE(students.created_at, CURRENT_TIMESTAMP), NULL,
                   COALESCE(students.created_at, CURRENT_TIMESTAMP)
            FROM students
            JOIN sections ON sections.id = students.section_id
            """
        ).bindparams(sa.bindparam("is_current", type_=sa.Boolean())),
        {"is_current": True},
    )

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("sections", recreate="always") as batch_op:
            batch_op.alter_column("batch_id", existing_type=sa.Integer(), nullable=False)
            batch_op.drop_constraint("uq_dept_year_section", type_="unique")
            batch_op.create_unique_constraint(
                "uq_batch_dept_year_section",
                ["batch_id", "department_id", "year_id", "name"],
            )
        with op.batch_alter_table("subjects", recreate="always") as batch_op:
            batch_op.alter_column("batch_id", existing_type=sa.Integer(), nullable=False)
            batch_op.drop_constraint("uq_subject_department_year_semester_name", type_="unique")
            batch_op.create_unique_constraint(
                "uq_subject_batch_department_year_semester_name",
                ["batch_id", "department_id", "year_id", "semester_id", "name"],
            )
        with op.batch_alter_table("exams", recreate="always") as batch_op:
            batch_op.alter_column("batch_id", existing_type=sa.Integer(), nullable=False)
            batch_op.create_unique_constraint(
                "uq_exam_batch_class_subject_name",
                ["batch_id", "department_id", "year_id", "semester_id", "section_id", "subject_id", "name"],
            )
        with op.batch_alter_table("students", recreate="always") as batch_op:
            batch_op.alter_column("batch_id", existing_type=sa.Integer(), nullable=False)
            batch_op.alter_column("section_id", existing_type=sa.Integer(), nullable=True)
    else:
        op.alter_column("sections", "batch_id", existing_type=sa.Integer(), nullable=False)
        op.drop_constraint("uq_dept_year_section", "sections", type_="unique")
        op.create_unique_constraint(
            "uq_batch_dept_year_section", "sections",
            ["batch_id", "department_id", "year_id", "name"],
        )
        op.alter_column("subjects", "batch_id", existing_type=sa.Integer(), nullable=False)
        op.drop_constraint("uq_subject_department_year_semester_name", "subjects", type_="unique")
        op.create_unique_constraint(
            "uq_subject_batch_department_year_semester_name", "subjects",
            ["batch_id", "department_id", "year_id", "semester_id", "name"],
        )
        op.alter_column("exams", "batch_id", existing_type=sa.Integer(), nullable=False)
        op.create_unique_constraint(
            "uq_exam_batch_class_subject_name", "exams",
            ["batch_id", "department_id", "year_id", "semester_id", "section_id", "subject_id", "name"],
        )
        op.alter_column("students", "batch_id", existing_type=sa.Integer(), nullable=False)
        op.alter_column("students", "section_id", existing_type=sa.Integer(), nullable=True)

    op.create_index("idx_section_lookup", "sections", ["batch_id", "department_id", "year_id"])
    if bind.dialect.name == "sqlite":
        violations = bind.exec_driver_sql("PRAGMA foreign_key_check").all()
        if violations:
            raise RuntimeError(f"Batch migration would leave SQLite foreign-key violations: {violations[:10]}")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text(
        "SELECT COUNT(*) FROM batches WHERE NOT (start_year = 2024 AND end_year = 2028)"
    )).scalar_one():
        raise RuntimeError("Cannot downgrade Batch migration after additional batches have been created.")
    if bind.execute(sa.text(
        """
        SELECT COUNT(*) FROM (
            SELECT student_id FROM student_academic_placements
            GROUP BY student_id HAVING COUNT(*) > 1
        )
        """
    )).scalar_one():
        raise RuntimeError(
            "Cannot downgrade after students have accumulated placement history; that history would be lost."
        )

    legacy_student_conflicts = bind.execute(sa.text(
        """
        SELECT section_id, register_no
        FROM students
        WHERE archived_at IS NULL
        GROUP BY section_id, register_no
        HAVING COUNT(*) > 1
        LIMIT 10
        """
    )).all()
    if legacy_student_conflicts:
        raise RuntimeError(
            "Cannot downgrade while active students share a register number in the same section; "
            "the prior revision enforced that constraint."
        )

    op.drop_index("idx_section_lookup", table_name="sections")
    op.drop_index("uq_student_current_academic_placement", table_name="student_academic_placements")
    op.drop_index("idx_placement_section_current", table_name="student_academic_placements")
    op.drop_index("ix_student_academic_placements_student_id", table_name="student_academic_placements")
    op.drop_index("ix_student_academic_placements_batch_id", table_name="student_academic_placements")
    op.drop_index("ix_student_academic_placements_section_id", table_name="student_academic_placements")
    op.drop_table("student_academic_placements")

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("students", recreate="always") as batch_op:
            batch_op.drop_constraint("fk_students_batch_id_batches", type_="foreignkey")
            batch_op.drop_column("batch_id")
            batch_op.alter_column("section_id", existing_type=sa.Integer(), nullable=False)
        with op.batch_alter_table("exams", recreate="always") as batch_op:
            batch_op.drop_constraint("uq_exam_batch_class_subject_name", type_="unique")
            batch_op.drop_constraint("fk_exams_batch_id_batches", type_="foreignkey")
            batch_op.drop_column("batch_id")
        with op.batch_alter_table("subjects", recreate="always") as batch_op:
            batch_op.drop_constraint("uq_subject_batch_department_year_semester_name", type_="unique")
            batch_op.drop_constraint("fk_subjects_batch_id_batches", type_="foreignkey")
            batch_op.drop_column("batch_id")
            batch_op.create_unique_constraint(
                "uq_subject_department_year_semester_name",
                ["department_id", "year_id", "semester_id", "name"],
            )
        with op.batch_alter_table("sections", recreate="always") as batch_op:
            batch_op.drop_constraint("uq_batch_dept_year_section", type_="unique")
            batch_op.drop_constraint("fk_sections_batch_id_batches", type_="foreignkey")
            batch_op.drop_column("batch_id")
            batch_op.create_unique_constraint(
                "uq_dept_year_section", ["department_id", "year_id", "name"]
            )
        op.create_index(
            "uq_student_section_register_no_active",
            "students",
            ["section_id", "register_no"],
            unique=True,
            sqlite_where=sa.text("archived_at IS NULL"),
        )
    else:
        for table_name, constraint_name in (
            ("exams", "uq_exam_batch_class_subject_name"),
            ("subjects", "uq_subject_batch_department_year_semester_name"),
            ("sections", "uq_batch_dept_year_section"),
        ):
            op.drop_constraint(constraint_name, table_name, type_="unique")
        for table_name in ("students", "exams", "subjects", "sections"):
            op.drop_constraint(f"fk_{table_name}_batch_id_batches", table_name, type_="foreignkey")
            op.drop_column(table_name, "batch_id")
        op.create_index(
            "uq_student_section_register_no_active",
            "students",
            ["section_id", "register_no"],
            unique=True,
            postgresql_where=sa.text("archived_at IS NULL"),
            sqlite_where=sa.text("archived_at IS NULL"),
        )
        op.create_unique_constraint(
            "uq_subject_department_year_semester_name",
            "subjects",
            ["department_id", "year_id", "semester_id", "name"],
        )
        op.create_unique_constraint(
            "uq_dept_year_section", "sections", ["department_id", "year_id", "name"]
        )

    op.drop_table("batches")
