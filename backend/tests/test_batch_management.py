from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from alembic import command
from alembic.config import Config
from sqlalchemy import Boolean, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.api.deps import get_db
from app.db.base import Base
from app.db.models import (
    Batch,
    CourseCOAttainmentInputs,
    CourseCOPOMapping,
    Department,
    Exam,
    ExamCoveredCO,
    ExamQuestion,
    Section,
    Semester,
    Student,
    StudentAcademicPlacement,
    StudentMark,
    Subject,
    Year,
)
from app.schemas.academic import BatchCreate, SectionCreate
from app.schemas.student import StudentCreate, StudentPlacementUpdate
from app.services.exam_service import ExamService
from app.services.marks_service import MarksApiService
from app.services.master_data_service import MasterDataService
from app.services.student_service import StudentService
from app.services.subject_service import SubjectService
from app.main import app


BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION_PATH = BACKEND_DIR / "alembic" / "versions" / "016_batch_student_placement.py"


@pytest.fixture
def academic_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False, expire_on_commit=False) as db:
        default_batch = Batch(batch_name="2024–28", start_year=2024, end_year=2028)
        next_batch = Batch(batch_name="2025–29", start_year=2025, end_year=2029)
        department = Department(name="Computer Science", code="CSE")
        third_year = Year(year_number=3, name="3rd Year")
        fourth_year = Year(year_number=4, name="4th Year")
        db.add_all([default_batch, next_batch, department, third_year, fourth_year])
        db.flush()

        semesters = [
            Semester(semester_number=5, name="Semester 5", year=third_year),
            Semester(semester_number=6, name="Semester 6", year=third_year),
            Semester(semester_number=7, name="Semester 7", year=fourth_year),
            Semester(semester_number=8, name="Semester 8", year=fourth_year),
        ]
        db.add_all(semesters)
        db.flush()
        sections = [
            Section(name="A", batch=default_batch, department=department, year=third_year),
            Section(name="B", batch=default_batch, department=department, year=fourth_year),
            Section(name="A", batch=next_batch, department=department, year=third_year),
        ]
        db.add_all(sections)
        db.flush()
        subjects = [
            Subject(
                name="DATA STRUCTURES",
                batch=batch,
                department=department,
                year=third_year,
                semester=semesters[0],
            )
            for batch in (default_batch, next_batch)
        ]
        subjects.append(Subject(name="LEGACY GLOBAL SUBJECT", batch=default_batch))
        db.add_all(subjects)
        db.flush()
        exams = [
            Exam(
                name="Internal Assessment 1",
                exam_type="INTERNAL_1",
                batch=batch,
                department=department,
                year=third_year,
                semester=semesters[0],
                section=section,
                subject=subject,
                pass_percentage=40,
                exam_date=date(2025, 6, 15),
            )
            for batch, section, subject in (
                (default_batch, sections[0], subjects[0]),
                (next_batch, sections[2], subjects[1]),
            )
        ]
        db.add_all(exams)
        db.flush()
        db.add_all([
            CourseCOPOMapping(subject_id=subjects[0].id, section_id=sections[0].id, mapping_data={"CO1": {}}),
            CourseCOPOMapping(subject_id=subjects[1].id, section_id=sections[2].id, mapping_data={"CO1": {}}),
            CourseCOAttainmentInputs(subject_id=subjects[0].id, section_id=sections[0].id, input_data={"CO1": 1}),
            CourseCOAttainmentInputs(subject_id=subjects[1].id, section_id=sections[2].id, input_data={"CO1": 2}),
        ])
        db.commit()
        yield {
            "db": db,
            "batches": (default_batch, next_batch),
            "department": department,
            "years": (third_year, fourth_year),
            "semesters": semesters,
            "sections": sections,
            "subjects": subjects,
            "exams": exams,
        }
    engine.dispose()


@pytest.fixture
def academic_api_client(academic_db):
    db = academic_db["db"]

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def batch_creation_api_client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'batch_creation.sqlite'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False, expire_on_commit=False) as db:
        default_batch = Batch(batch_name="2024–28", start_year=2024, end_year=2028)
        db.add(default_batch)
        db.commit()
        default_id = default_batch.id

        def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                yield client, db, default_id
        finally:
            app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def _legacy_database(path: Path, duplicate_register: bool = False) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        PRAGMA foreign_keys=ON;
        CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);
        INSERT INTO alembic_version VALUES ('015_course_obe_section_scope');
        CREATE TABLE departments (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, code VARCHAR(20) NOT NULL);
        CREATE TABLE years (id INTEGER PRIMARY KEY, year_number INTEGER NOT NULL, name VARCHAR(20) NOT NULL);
        CREATE TABLE semesters (
            id INTEGER PRIMARY KEY, semester_number INTEGER NOT NULL, name VARCHAR(20) NOT NULL,
            year_id INTEGER NOT NULL REFERENCES years(id)
        );
        CREATE TABLE sections (
            id INTEGER PRIMARY KEY, name VARCHAR(20) NOT NULL, department_id INTEGER NOT NULL REFERENCES departments(id),
            year_id INTEGER NOT NULL REFERENCES years(id), created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL, CONSTRAINT uq_dept_year_section UNIQUE(department_id, year_id, name)
        );
        CREATE INDEX idx_section_lookup ON sections(department_id, year_id);
        CREATE TABLE students (
            id INTEGER PRIMARY KEY, register_no VARCHAR(50) NOT NULL, name VARCHAR(100) NOT NULL,
            section_id INTEGER NOT NULL REFERENCES sections(id), archived_at DATETIME,
            created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
        );
        CREATE UNIQUE INDEX uq_student_section_register_no_active
            ON students(section_id, register_no) WHERE archived_at IS NULL;
        CREATE TABLE subjects (
            id INTEGER PRIMARY KEY, name VARCHAR(150) NOT NULL, department_id INTEGER REFERENCES departments(id),
            year_id INTEGER REFERENCES years(id), semester_id INTEGER REFERENCES semesters(id),
            is_active BOOLEAN NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,
            CONSTRAINT uq_subject_department_year_semester_name
                UNIQUE(department_id, year_id, semester_id, name)
        );
        CREATE TABLE exams (
            id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, exam_type VARCHAR(50) NOT NULL,
            department_id INTEGER NOT NULL REFERENCES departments(id), year_id INTEGER NOT NULL REFERENCES years(id),
            semester_id INTEGER NOT NULL REFERENCES semesters(id), section_id INTEGER NOT NULL REFERENCES sections(id),
            subject_id INTEGER NOT NULL REFERENCES subjects(id), pass_percentage NUMERIC NOT NULL, exam_date DATE,
            created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
        );
        CREATE TABLE student_marks (
            id INTEGER PRIMARY KEY, exam_id INTEGER NOT NULL REFERENCES exams(id),
            student_id INTEGER NOT NULL REFERENCES students(id), question_number VARCHAR(20) NOT NULL,
            obtained_mark NUMERIC NOT NULL
        );
        CREATE TABLE course_co_po_mappings (
            id INTEGER PRIMARY KEY, subject_id INTEGER NOT NULL REFERENCES subjects(id),
            section_id INTEGER REFERENCES sections(id), mapping_data JSON NOT NULL
        );
        CREATE TABLE course_co_attainment_inputs (
            id INTEGER PRIMARY KEY, subject_id INTEGER NOT NULL REFERENCES subjects(id),
            section_id INTEGER REFERENCES sections(id), input_data JSON NOT NULL
        );
        INSERT INTO departments VALUES (1, 'Computer Science', 'CSE');
        INSERT INTO years VALUES (3, 3, '3rd Year');
        INSERT INTO semesters VALUES (5, 5, 'Semester 5', 3);
        INSERT INTO sections VALUES (1, 'A', 1, 3, '2024-01-01', '2024-01-01');
        INSERT INTO students VALUES (1, 'TEST-REG-0001', 'Student One', 1, NULL, '2024-01-01', '2024-01-01');
        INSERT INTO subjects VALUES (1, 'DATA STRUCTURES', 1, 3, 5, 1, '2024-01-01', '2024-01-01');
        INSERT INTO subjects VALUES (2, 'LEGACY UNSCOPED', NULL, NULL, NULL, 1, '2024-01-01', '2024-01-01');
        INSERT INTO exams VALUES (1, 'Internal Assessment 1', 'INTERNAL_1', 1, 3, 5, 1, 2, 40, NULL, '2024-01-01', '2024-01-01');
        INSERT INTO student_marks VALUES (1, 1, 1, 'Q1', 8);
        INSERT INTO course_co_po_mappings VALUES (1, 1, 1, '{"CO1":{"PO1":3}}');
        INSERT INTO course_co_attainment_inputs VALUES (1, 1, 1, '{"CO1":2}');
        """
    )
    if duplicate_register:
        connection.executescript(
            """
            INSERT INTO sections VALUES (2, 'B', 1, 3, '2024-01-01', '2024-01-01');
            INSERT INTO students VALUES (2, 'TEST-REG-0001', 'Another Student', 2, '2025-01-01', '2024-01-01', '2024-01-01');
            INSERT INTO students VALUES (3, 'TEST-REG-0002', 'Third Student', 1, NULL, '2024-01-01', '2024-01-01');
            INSERT INTO students VALUES (4, 'TEST-REG-0003', 'Fourth Student', 2, NULL, '2024-01-01', '2024-01-01');
            """
        )
    connection.commit()
    connection.close()


def _run_batch_migration(database_path: Path, backup_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        f"sqlite:///{database_path.as_posix()}",
    )
    monkeypatch.setenv("OBE_DB_BACKUP_PATH", str(backup_path))
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "016_batch_student_placement")


def _create_sqlite_backup(source: Path, destination: Path) -> None:
    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as backup_db:
        source_db.backup(backup_db)


def test_migration_backfills_default_batch_and_preserves_legacy_records(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy.sqlite"
    backup_path = tmp_path / "legacy-backup.sqlite"
    _legacy_database(database_path)
    _create_sqlite_backup(database_path, backup_path)

    bound_boolean_values = {}

    def capture_boolean_bindings(_connection, statement, _multiparams, params, _options):
        sql = getattr(statement, "text", "")
        parameter_name = None
        if "INSERT INTO batches" in sql:
            parameter_name = "is_active"
        elif "INSERT INTO student_academic_placements" in sql:
            parameter_name = "is_current"
        if parameter_name is not None:
            bind = statement.compile().binds[parameter_name]
            bound_boolean_values[parameter_name] = (params[parameter_name], bind.type)

    event.listen(Engine, "before_execute", capture_boolean_bindings)
    try:
        _run_batch_migration(database_path, backup_path, monkeypatch)
    finally:
        event.remove(Engine, "before_execute", capture_boolean_bindings)

    assert set(bound_boolean_values) == {"is_active", "is_current"}
    for value, bind_type in bound_boolean_values.values():
        assert value is True
        assert isinstance(bind_type, Boolean)

    with sqlite3.connect(database_path) as db:
        batch_id = db.execute("SELECT id FROM batches WHERE batch_name = '2024–28'").fetchone()[0]
        assert db.execute("SELECT is_active FROM batches WHERE id = ?", (batch_id,)).fetchone() == (1,)
        assert db.execute("SELECT batch_id FROM students WHERE id = 1").fetchone() == (batch_id,)
        assert db.execute("SELECT batch_id FROM sections WHERE id = 1").fetchone() == (batch_id,)
        assert db.execute("SELECT batch_id FROM subjects WHERE id IN (1, 2) ORDER BY id").fetchall() == [
            (batch_id,),
            (batch_id,),
        ]
        assert db.execute("SELECT batch_id FROM exams WHERE id = 1").fetchone() == (batch_id,)
        assert db.execute(
            "SELECT department_id, year_id, semester_id FROM subjects WHERE id = 2"
        ).fetchone() == (1, 3, 5)
        assert db.execute("SELECT subject_id FROM exams WHERE id = 1").fetchone() == (2,)
        assert db.execute(
            "SELECT student_id, batch_id, department_id, year_id, semester_id, section_id, is_current "
            "FROM student_academic_placements"
        ).fetchone() == (1, batch_id, 1, 3, None, 1, 1)
        assert db.execute("SELECT id, student_id, exam_id, obtained_mark FROM student_marks").fetchall() == [
            (1, 1, 1, 8),
        ]
        assert db.execute("SELECT id, subject_id, section_id FROM course_co_po_mappings").fetchall() == [
            (1, 1, 1),
        ]
        assert db.execute("SELECT id, subject_id, section_id FROM course_co_attainment_inputs").fetchall() == [
            (1, 1, 1),
        ]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "016_batch_student_placement",
        )


def test_migration_preserves_duplicate_batch_register_conflicts(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy-duplicates.sqlite"
    backup_path = tmp_path / "legacy-duplicates-backup.sqlite"
    _legacy_database(database_path, duplicate_register=True)
    with sqlite3.connect(database_path) as db:
        db.execute(
            "UPDATE students SET register_no = 'TEST-REG-0349', name = 'Sample Student 1', section_id = 2, "
            "archived_at = '2026-09-27 05:17:29.495796' WHERE id = 1"
        )
        db.execute(
            "UPDATE students SET register_no = 'TEST-REG-0349', name = 'Sample Student 2', archived_at = NULL WHERE id = 2"
        )
        db.execute("UPDATE students SET register_no = 'TEST-REG-0364', name = 'Sample Student 3' WHERE id = 3")
        db.execute(
            "UPDATE students SET register_no = 'TEST-REG-0364', name = 'Sample Student 4' WHERE id = 4"
        )
        db.execute("UPDATE student_marks SET student_id = 2 WHERE id = 1")
    _create_sqlite_backup(database_path, backup_path)

    _run_batch_migration(database_path, backup_path, monkeypatch)

    with sqlite3.connect(database_path) as db:
        assert db.execute(
            "SELECT id, register_no, name, archived_at, batch_id FROM students ORDER BY id"
        ).fetchall() == [
            (1, "TEST-REG-0349", "Sample Student 1", "2026-09-27 05:17:29.495796", 1),
            (2, "TEST-REG-0349", "Sample Student 2", None, 1),
            (3, "TEST-REG-0364", "Sample Student 3", None, 1),
            (4, "TEST-REG-0364", "Sample Student 4", None, 1),
        ]
        assert db.execute("SELECT COUNT(*) FROM student_academic_placements").fetchone() == (4,)
        assert db.execute("SELECT COUNT(*) FROM student_marks").fetchone() == (1,)
        assert db.execute("SELECT student_id FROM student_marks WHERE id = 1").fetchone() == (2,)
        student_indexes = {
            row[1] for row in db.execute("PRAGMA index_list('students')")
        }
        assert "uq_student_batch_register_no" not in student_indexes
        assert "uq_student_section_register_no_active" not in student_indexes
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "016_batch_student_placement",
        )


def test_logical_section_migration_snapshots_placements_on_an_isolated_database(tmp_path, monkeypatch):
    database_path = tmp_path / "logical-section.sqlite"
    backup_path = tmp_path / "logical-section-backup.sqlite"
    _legacy_database(database_path)
    _create_sqlite_backup(database_path, backup_path)

    _run_batch_migration(database_path, backup_path, monkeypatch)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "018_student_placement_logical_section")

    with sqlite3.connect(database_path) as db:
        assert db.execute(
            "SELECT section_id, section_name, is_current FROM student_academic_placements"
        ).fetchone() == (1, "A", 1)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "018_student_placement_logical_section",
        )


def test_two_batches_can_share_academic_labels_without_sharing_records(academic_db):
    db = academic_db["db"]
    batch_one, batch_two = academic_db["batches"]
    first_section, second_section = academic_db["sections"][0], academic_db["sections"][2]
    department = academic_db["department"]
    third_year = academic_db["years"][0]
    semester_five = academic_db["semesters"][0]

    first_student = StudentService(db).create_student(StudentCreate(
        register_no="TEST-REG-0301",
        name="Student One",
        section_id=first_section.id,
        batch_id=batch_one.id,
        semester_id=academic_db["semesters"][0].id,
    ))
    second_student = StudentService(db).create_student(StudentCreate(
        register_no="TEST-REG-0301",
        name="Student One",
        section_id=second_section.id,
        batch_id=batch_two.id,
        semester_id=academic_db["semesters"][0].id,
    ))
    unrelated_student = StudentService(db).create_student(StudentCreate(
        register_no="TEST-REG-0999",
        name="Unrelated Student",
        section_id=academic_db["sections"][1].id,
        batch_id=batch_one.id,
        semester_id=academic_db["semesters"][2].id,
    ))
    db.add_all([
        StudentMark(exam_id=academic_db["exams"][0].id, student_id=first_student.id, question_number="Q1", obtained_mark=8),
        StudentMark(exam_id=academic_db["exams"][0].id, student_id=unrelated_student.id, question_number="Q1", obtained_mark=2),
        StudentMark(exam_id=academic_db["exams"][1].id, student_id=second_student.id, question_number="Q1", obtained_mark=9),
    ])
    db.commit()

    assert first_student.id != second_student.id
    assert first_section.name == second_section.name == "A"
    assert first_section.year_id == second_section.year_id
    default_subjects = SubjectService(db).list_subjects(
        department.id,
        third_year.id,
        semester_five.id,
        batch_id=batch_one.id,
    )
    next_batch_subjects = SubjectService(db).list_subjects(
        department.id,
        third_year.id,
        semester_five.id,
        batch_id=batch_two.id,
    )
    assert [subject.id for subject in default_subjects] == [academic_db["subjects"][0].id]
    assert next_batch_subjects == [academic_db["subjects"][1]]
    assert [exam.id for exam in ExamService(db).list_exams(batch_id=batch_one.id)] == [academic_db["exams"][0].id]
    assert [exam.id for exam in ExamService(db).list_exams(batch_id=batch_two.id)] == [academic_db["exams"][1].id]
    assert [row["id"] for row in MarksApiService(db).get_exam_roster(academic_db["exams"][0].id)] == [
        first_student.id,
    ]
    assert [row["id"] for row in MarksApiService(db).get_exam_roster(academic_db["exams"][1].id)] == [
        second_student.id,
    ]


def test_student_move_preserves_identity_history_and_historical_marks(academic_db):
    db = academic_db["db"]
    batch_one = academic_db["batches"][0]
    student = StudentService(db).create_student(StudentCreate(
        register_no="TEST-REG-0301",
        name="Student One",
        section_id=academic_db["sections"][0].id,
        batch_id=batch_one.id,
        semester_id=academic_db["semesters"][0].id,
    ))
    db.add(StudentMark(
        exam_id=academic_db["exams"][0].id,
        student_id=student.id,
        question_number="Q1",
        obtained_mark=8,
    ))
    db.commit()
    original_student_id = student.id
    old_section_id = academic_db["sections"][0].id

    moved_student = StudentService(db).move_student(
        original_student_id,
        StudentPlacementUpdate(
            section_id=academic_db["sections"][1].id,
            semester_id=academic_db["semesters"][2].id,
        ),
    )

    history = StudentService(db).get_student_placements(original_student_id)
    assert moved_student.id == original_student_id
    assert moved_student.section_id == academic_db["sections"][1].id
    assert db.query(Student).filter(Student.batch_id == batch_one.id).count() == 1
    assert [(row.section_id, row.semester_id, row.is_current) for row in history] == [
        (old_section_id, academic_db["semesters"][0].id, False),
        (academic_db["sections"][1].id, academic_db["semesters"][2].id, True),
    ]
    assert db.query(StudentMark).filter(
        StudentMark.exam_id == academic_db["exams"][0].id,
        StudentMark.student_id == original_student_id,
    ).one().obtained_mark == 8
    assert db.query(CourseCOPOMapping).count() == 2
    assert db.query(CourseCOAttainmentInputs).count() == 2


def test_changing_year_with_same_cohort_does_not_move_student_placement(
    academic_db,
    academic_api_client,
):
    db = academic_db["db"]
    batch = academic_db["batches"][0]
    department = academic_db["department"]
    original_section = academic_db["sections"][0]
    student = StudentService(db).create_student(StudentCreate(
        register_no="TEST-REG-YEARSELECTOR",
        name="Year Selector Student",
        section_id=original_section.id,
        batch_id=batch.id,
        semester_id=academic_db["semesters"][0].id,
    ))
    second_year = Year(year_number=2, name="2nd Year")
    db.add(second_year)
    db.flush()
    semester_three = Semester(
        semester_number=3,
        name="Semester 3",
        year=second_year,
    )
    second_year_section = Section(
        name=original_section.name,
        batch=batch,
        department=department,
        year=second_year,
    )
    db.add_all([semester_three, second_year_section])
    db.commit()
    original_placements = [
        (
            placement.id,
            placement.year_id,
            placement.semester_id,
            placement.section_id,
            placement.is_current,
            placement.effective_from,
            placement.effective_to,
        )
        for placement in db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id == student.id
        ).order_by(StudentAcademicPlacement.id)
    ]

    response = academic_api_client.put(
        f"/api/students/{student.id}/placement",
        json={
            "section_id": second_year_section.id,
            "semester_id": semester_three.id,
        },
    )

    assert response.status_code == 409
    db.expire_all()
    assert db.query(Student.section_id).filter(Student.id == student.id).scalar() == original_section.id
    assert [
        (
            placement.id,
            placement.year_id,
            placement.semester_id,
            placement.section_id,
            placement.is_current,
            placement.effective_from,
            placement.effective_to,
        )
        for placement in db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id == student.id
        ).order_by(StudentAcademicPlacement.id)
    ] == original_placements


def test_creating_batch_does_not_change_default_batch_records(academic_db):
    db = academic_db["db"]
    default_batch = academic_db["batches"][0]
    original_sections = db.query(Section).filter(Section.batch_id == default_batch.id).count()
    original_students = db.query(Student).filter(Student.batch_id == default_batch.id).count()

    created = MasterDataService(db).create_batch(BatchCreate(
        batch_name="2026–30",
        start_year=2026,
        end_year=2030,
    ))

    assert created.id != default_batch.id
    assert db.query(Section).filter(Section.batch_id == default_batch.id).count() == original_sections
    assert db.query(Student).filter(Student.batch_id == default_batch.id).count() == original_students
    assert db.query(Batch).filter(Batch.start_year == 2024, Batch.end_year == 2028).count() == 1


def test_batch_creation_parses_name_and_keeps_existing_default_unchanged(batch_creation_api_client):
    client, db, default_id = batch_creation_api_client
    default_before = db.query(Batch).filter(Batch.id == default_id).one()

    first = client.post("/api/academic/batches", json={"batch_name": "2025–29"})
    second = client.post("/api/academic/batches", json={"batch_name": " 2026–30 "})

    assert first.status_code == 201, first.text
    assert first.json()["batch_name"] == "2025–29"
    assert first.json()["start_year"] == 2025
    assert first.json()["end_year"] == 2029
    assert second.status_code == 201, second.text
    assert second.json()["batch_name"] == "2026–30"
    assert second.json()["start_year"] == 2026
    assert second.json()["end_year"] == 2030
    db.refresh(default_before)
    assert (
        default_before.batch_name,
        default_before.start_year,
        default_before.end_year,
    ) == ("2024–28", 2024, 2028)


@pytest.mark.parametrize("batch_name", ["2025", "2025–27", "abc", "2029–25"])
def test_batch_creation_rejects_invalid_batch_name(batch_creation_api_client, batch_name):
    client, db, default_id = batch_creation_api_client

    response = client.post("/api/academic/batches", json={"batch_name": batch_name})

    assert response.status_code == 400
    assert response.json()["detail"] == "Enter batch in the format 2025–29."
    assert db.query(Batch).count() == 1
    assert db.query(Batch).filter(Batch.id == default_id).one_or_none() is not None


def test_batch_creation_normalizes_duplicate_name_and_year_range(batch_creation_api_client):
    client, db, _default_id = batch_creation_api_client
    created = client.post("/api/academic/batches", json={"batch_name": "2025-29"})
    duplicate_name = client.post("/api/academic/batches", json={"batch_name": "2025–29"})
    duplicate_range = client.post("/api/academic/batches", json={"batch_name": "2025–2029"})

    assert created.status_code == 201
    assert duplicate_name.status_code == 400
    assert duplicate_range.status_code == 400
    assert db.query(Batch).filter(
        Batch.start_year == 2025,
        Batch.end_year == 2029,
    ).count() == 1


def test_empty_batch_can_be_deleted_without_affecting_populated_batches(academic_db):
    db = academic_db["db"]
    empty_batch = MasterDataService(db).create_batch(BatchCreate(
        batch_name="2030–34",
        start_year=2030,
        end_year=2034,
    ))

    assert MasterDataService(db).get_batch_deletion_status(empty_batch.id) == {
        "can_delete": True,
        "reason": None,
    }
    assert MasterDataService(db).delete_batch(empty_batch.id)
    assert db.query(Batch).filter(Batch.id == empty_batch.id).one_or_none() is None
    assert db.query(Batch).filter(Batch.id.in_([batch.id for batch in academic_db["batches"]])).count() == 2
    assert db.query(Student).filter(Student.batch_id == academic_db["batches"][0].id).count() == 0
    assert db.query(Section).filter(Section.batch_id == academic_db["batches"][0].id).count() == 2


def test_populated_batch_is_permanently_deleted_without_affecting_other_batch(academic_db):
    db = academic_db["db"]
    batch, other_batch = academic_db["batches"]
    target_exam, other_exam = academic_db["exams"]
    target_section, _, other_section = academic_db["sections"]
    target_subject, other_subject = academic_db["subjects"][:2]
    target_student = _add_deletion_test_student(
        db, batch, target_section, target_exam, "TEST-REG-0001"
    )
    other_student = _add_deletion_test_student(
        db, other_batch, other_section, other_exam, "TEST-REG-0001"
    )

    result = MasterDataService(db).delete_batch(batch.id)

    assert result == {
        "deleted_id": batch.id,
        "message": "Batch '2024–28' permanently deleted.",
    }
    assert db.query(Batch).filter(Batch.id == batch.id).one_or_none() is None
    assert db.query(Student).filter(Student.id == target_student.id).count() == 0
    assert db.query(StudentMark).filter(StudentMark.student_id == target_student.id).count() == 0
    assert db.query(StudentAcademicPlacement).filter(
        StudentAcademicPlacement.student_id == target_student.id
    ).count() == 0
    assert db.query(Section).filter(Section.batch_id == batch.id).count() == 0
    assert db.query(Subject).filter(Subject.batch_id == batch.id).count() == 0
    assert db.query(Exam).filter(Exam.batch_id == batch.id).count() == 0
    assert db.query(ExamQuestion).filter(ExamQuestion.exam_id == target_exam.id).count() == 0
    assert db.query(ExamCoveredCO).filter(ExamCoveredCO.exam_id == target_exam.id).count() == 0
    assert db.query(CourseCOPOMapping).filter(
        CourseCOPOMapping.subject_id == target_subject.id
    ).count() == 0
    assert db.query(CourseCOAttainmentInputs).filter(
        CourseCOAttainmentInputs.subject_id == target_subject.id
    ).count() == 0
    assert db.query(Batch).filter(Batch.id == other_batch.id).one_or_none() is other_batch
    assert db.query(Student).filter(Student.id == other_student.id).one_or_none() is other_student
    assert db.query(StudentMark).filter(StudentMark.student_id == other_student.id).count() == 1
    assert db.query(Section).filter(Section.id == other_section.id).one_or_none() is other_section
    assert db.query(Subject).filter(Subject.id == other_subject.id).one_or_none() is other_subject
    assert db.query(Exam).filter(Exam.id == other_exam.id).one_or_none() is other_exam
    assert db.query(CourseCOPOMapping).filter(
        CourseCOPOMapping.subject_id == other_subject.id
    ).count() == 1
    assert db.query(CourseCOAttainmentInputs).filter(
        CourseCOAttainmentInputs.subject_id == other_subject.id
    ).count() == 1


def _add_deletion_test_student(db, batch, section, exam, register_no):
    student = Student(
        register_no=register_no,
        name=f"Student {register_no}",
        batch_id=batch.id,
        section_id=section.id,
    )
    db.add(student)
    db.flush()
    db.add(StudentAcademicPlacement(
        student_id=student.id,
        batch_id=batch.id,
        department_id=section.department_id,
        year_id=section.year_id,
        semester_id=exam.semester_id,
        section_id=section.id,
        is_current=True,
    ))
    db.add_all([
        ExamQuestion(
            exam_id=exam.id,
            question_number="Q1",
            max_marks=10,
            co_code="CO1",
        ),
        ExamCoveredCO(exam_id=exam.id, co_code="CO1"),
        StudentMark(
            exam_id=exam.id,
            student_id=student.id,
            question_number="Q1",
            obtained_mark=8,
        ),
    ])
    db.commit()
    return student


def _get_or_create_cohort_sections(db, batch, department, cohort_name):
    year_names = {
        1: "1st Year",
        2: "2nd Year",
        3: "3rd Year",
        4: "4th Year",
    }
    sections = []
    for year_number in range(1, 5):
        year = db.query(Year).filter(Year.year_number == year_number).one_or_none()
        if year is None:
            year = Year(year_number=year_number, name=year_names[year_number])
            db.add(year)
            db.flush()

        for semester_number in (year_number * 2 - 1, year_number * 2):
            semester = db.query(Semester).filter(
                Semester.semester_number == semester_number
            ).one_or_none()
            if semester is None:
                db.add(Semester(
                    semester_number=semester_number,
                    name=f"Semester {semester_number}",
                    year=year,
                ))

        section = db.query(Section).filter(
            Section.batch_id == batch.id,
            Section.department_id == department.id,
            Section.year_id == year.id,
            Section.name == cohort_name,
        ).one_or_none()
        if section is None:
            section = Section(
                name=cohort_name,
                batch_id=batch.id,
                department_id=department.id,
                year_id=year.id,
            )
            db.add(section)
            db.flush()
        sections.append(section)

    db.commit()
    return sections


@pytest.mark.parametrize("cohort_name", ["A", "B", "C"])
def test_student_roster_carries_cohort_section_across_all_years_without_duplicates(
    academic_db,
    academic_api_client,
    cohort_name,
):
    db = academic_db["db"]
    batch, other_batch = academic_db["batches"]
    department = academic_db["department"]
    sections = _get_or_create_cohort_sections(db, batch, department, cohort_name)
    other_cohort_sections = _get_or_create_cohort_sections(
        db, batch, department, "B" if cohort_name != "B" else "C"
    )
    other_batch_sections = _get_or_create_cohort_sections(
        db, other_batch, department, cohort_name
    )
    semester_id = db.query(Semester.id).filter(
        Semester.year_id == sections[0].year_id
    ).order_by(Semester.semester_number).first()[0]
    student_response = academic_api_client.post(
        "/api/students",
        json={
            "register_no": f"TEST-REG-COHORT{cohort_name}",
            "name": f"Cohort {cohort_name} Student",
            "section_id": sections[0].id,
            "semester_id": semester_id,
        },
    )
    assert student_response.status_code == 201, student_response.text
    student_id = student_response.json()["id"]
    subject = Subject(
        name=f"COHORT {cohort_name} FIRST YEAR SUBJECT",
        batch=batch,
        department=department,
        year=sections[0].year,
        semester=db.query(Semester).filter(Semester.id == semester_id).one(),
    )
    db.add(subject)
    db.flush()
    exam = Exam(
        name=f"COHORT {cohort_name} FIRST YEAR EXAM",
        exam_type="INTERNAL_1",
        batch=batch,
        department=department,
        year=sections[0].year,
        semester=subject.semester,
        section=sections[0],
        subject=subject,
        pass_percentage=40,
    )
    db.add(exam)
    db.flush()
    mark = StudentMark(
        exam_id=exam.id,
        student_id=student_id,
        question_number="Q1",
        obtained_mark=7,
    )
    db.add_all([
        ExamQuestion(
            exam_id=exam.id,
            question_number="Q1",
            max_marks=10,
            co_code="CO1",
        ),
        mark,
    ])
    foreign_student = Student(
        register_no=f"TEST-REG-COHORT{cohort_name}",
        name=f"Other Batch {cohort_name}",
        batch_id=other_batch.id,
        section_id=other_batch_sections[0].id,
    )
    db.add(foreign_student)
    db.flush()
    foreign_semester_id = db.query(Semester.id).filter(
        Semester.year_id == other_batch_sections[0].year_id
    ).order_by(Semester.semester_number).first()[0]
    db.add(StudentAcademicPlacement(
        student_id=foreign_student.id,
        batch_id=other_batch.id,
        department_id=department.id,
        year_id=other_batch_sections[0].year_id,
        semester_id=foreign_semester_id,
        section_id=other_batch_sections[0].id,
        is_current=True,
    ))
    other_cohort_student = Student(
        register_no=f"TEST-REG-OTHERCOHORT{cohort_name}",
        name=f"Other cohort {cohort_name}",
        batch_id=batch.id,
        section_id=other_cohort_sections[0].id,
    )
    db.add(other_cohort_student)
    db.flush()
    db.add(StudentAcademicPlacement(
        student_id=other_cohort_student.id,
        batch_id=batch.id,
        department_id=department.id,
        year_id=other_cohort_sections[0].year_id,
        semester_id=semester_id,
        section_id=other_cohort_sections[0].id,
        is_current=True,
    ))
    db.commit()
    original_mark_id = mark.id

    assert db.query(Student).filter(
        Student.batch_id == batch.id,
        Student.register_no == f"TEST-REG-COHORT{cohort_name}",
    ).count() == 1
    original_section_id = db.query(Student.section_id).filter(
        Student.id == student_id
    ).scalar()
    original_placements = [
        (
            placement.id,
            placement.year_id,
            placement.semester_id,
            placement.section_id,
            placement.is_current,
            placement.effective_from,
            placement.effective_to,
        )
        for placement in db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id == student_id
        ).order_by(StudentAcademicPlacement.id)
    ]
    for section in sections:
        section_roster_response = academic_api_client.get(
            f"/api/sections/{section.id}/students"
        )
        assert section_roster_response.status_code == 200
        assert {student["id"] for student in section_roster_response.json()} == {student_id}
    db.expire_all()
    assert db.query(Student.section_id).filter(Student.id == student_id).scalar() == original_section_id
    assert [
        (
            placement.id,
            placement.year_id,
            placement.semester_id,
            placement.section_id,
            placement.is_current,
            placement.effective_from,
            placement.effective_to,
        )
        for placement in db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id == student_id
        ).order_by(StudentAcademicPlacement.id)
    ] == original_placements
    wrong_cohort_roster = academic_api_client.get(
        f"/api/sections/{other_cohort_sections[0].id}/students"
    ).json()
    assert {student["id"] for student in wrong_cohort_roster} == {
        other_cohort_student.id
    }
    assert db.query(Student).filter(Student.id == foreign_student.id).one_or_none() is foreign_student
    assert foreign_student.batch_id == other_batch.id
    db.refresh(mark)
    assert mark.id == original_mark_id
    assert mark.student_id == student_id
    assert mark.exam_id == exam.id
    assert mark.obtained_mark == 7


@pytest.mark.parametrize("cohort_name", ["A", "B", "C"])
def test_existing_third_year_student_is_visible_in_corresponding_year_sections(
    academic_db,
    academic_api_client,
    cohort_name,
):
    db = academic_db["db"]
    batch = academic_db["batches"][0]
    department = academic_db["department"]
    sections = _get_or_create_cohort_sections(db, batch, department, cohort_name)
    year_three_section = sections[2]
    student = Student(
        register_no=f"TEST-REG-YEAR3{cohort_name}",
        name=f"Existing Year Three {cohort_name}",
        batch_id=batch.id,
        section_id=year_three_section.id,
    )
    db.add(student)
    db.flush()
    placement = StudentAcademicPlacement(
        student_id=student.id,
        batch_id=batch.id,
        department_id=department.id,
        year_id=year_three_section.year_id,
        semester_id=academic_db["semesters"][0].id,
        section_id=year_three_section.id,
        is_current=True,
    )
    db.add(placement)
    mismatched_batch_student = Student(
        register_no=f"TEST-REG-MISMATCH{cohort_name}",
        name=f"Mismatched Batch {cohort_name}",
        batch_id=academic_db["batches"][1].id,
        section_id=year_three_section.id,
    )
    db.add(mismatched_batch_student)
    db.commit()

    for section in sections:
        response = academic_api_client.get(f"/api/sections/{section.id}/students")
        assert response.status_code == 200
        assert {item["id"] for item in response.json()} == {student.id}

    assert db.query(Student).filter(
        Student.batch_id == batch.id,
        Student.register_no == student.register_no,
    ).count() == 1
    assert db.query(StudentAcademicPlacement).filter(
        StudentAcademicPlacement.student_id == student.id
    ).count() == 1
    db.refresh(placement)
    assert placement.section_id == year_three_section.id
    assert placement.year_id == year_three_section.year_id
    assert placement.is_current is True


def test_exam_roster_uses_batch_department_and_cohort_section_across_years(
    academic_db,
    academic_api_client,
):
    db = academic_db["db"]
    batch, other_batch = academic_db["batches"]
    department = academic_db["department"]
    section_a_by_year = _get_or_create_cohort_sections(db, batch, department, "A")
    section_b_by_year = _get_or_create_cohort_sections(db, batch, department, "B")
    foreign_a_by_year = _get_or_create_cohort_sections(db, other_batch, department, "A")
    source_section = section_a_by_year[0]
    target_section = section_a_by_year[3]
    source_semester = db.query(Semester).filter(
        Semester.year_id == source_section.year_id
    ).order_by(Semester.semester_number).first()
    target_semester = db.query(Semester).filter(
        Semester.year_id == target_section.year_id
    ).order_by(Semester.semester_number).first()
    target_subject = Subject(
        name="COHORT TARGET YEAR SUBJECT",
        batch=batch,
        department=department,
        year=target_section.year,
        semester=target_semester,
    )
    source_subject = Subject(
        name="COHORT SOURCE YEAR SUBJECT",
        batch=batch,
        department=department,
        year=source_section.year,
        semester=source_semester,
    )
    db.add_all([target_subject, source_subject])
    db.flush()
    source_exam = Exam(
        name="First Year Cohort Exam",
        exam_type="INTERNAL_1",
        batch=batch,
        department=department,
        year=source_section.year,
        semester=source_semester,
        section=source_section,
        subject=source_subject,
        pass_percentage=40,
        exam_date=None,
    )
    target_exam = Exam(
        name="Fourth Year Cohort Exam",
        exam_type="INTERNAL_1",
        batch=batch,
        department=department,
        year=target_section.year,
        semester=target_semester,
        section=target_section,
        subject=target_subject,
        pass_percentage=40,
        exam_date=None,
    )
    db.add_all([source_exam, target_exam])
    db.flush()
    cohort_student = Student(
        register_no="TEST-REG-COHORTEXAM",
        name="Cohort Exam Student",
        batch_id=batch.id,
        section_id=source_section.id,
    )
    other_cohort_student = Student(
        register_no="TEST-REG-BCOHORTEXAM",
        name="Different Cohort Student",
        batch_id=batch.id,
        section_id=section_b_by_year[0].id,
    )
    foreign_batch_student = Student(
        register_no="TEST-REG-COHORTEXAM",
        name="Foreign Batch Student",
        batch_id=other_batch.id,
        section_id=foreign_a_by_year[0].id,
    )
    db.add_all([cohort_student, other_cohort_student, foreign_batch_student])
    db.flush()
    db.add_all([
        StudentAcademicPlacement(
            student_id=student.id,
            batch_id=student.batch_id,
            department_id=department.id,
            year_id=student.section.year_id,
            semester_id=source_semester.id,
            section_id=student.section_id,
            is_current=True,
        )
        for student in (cohort_student, other_cohort_student, foreign_batch_student)
    ])
    db.add_all([
        ExamQuestion(exam_id=source_exam.id, question_number="Q1", max_marks=10, co_code="CO1"),
        ExamQuestion(exam_id=target_exam.id, question_number="Q1", max_marks=10, co_code="CO1"),
        StudentMark(
            exam_id=source_exam.id,
            student_id=cohort_student.id,
            question_number="Q1",
            obtained_mark=7,
        ),
    ])
    db.commit()
    original_mark = db.query(StudentMark).filter(
        StudentMark.exam_id == source_exam.id,
        StudentMark.student_id == cohort_student.id,
    ).one()
    original_mark_id = original_mark.id

    response = academic_api_client.get(f"/api/exams/{target_exam.id}/roster")

    assert response.status_code == 200
    roster_ids = {student["id"] for student in response.json()}
    assert cohort_student.id in roster_ids
    assert other_cohort_student.id not in roster_ids
    assert foreign_batch_student.id not in roster_ids
    preserved_mark = db.query(StudentMark).filter(StudentMark.id == original_mark_id).one()
    assert preserved_mark.obtained_mark == 7
    assert preserved_mark.exam_id == source_exam.id
    assert preserved_mark.student_id == cohort_student.id


def test_last_remaining_batch_cannot_be_deleted(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'single_batch.sqlite'}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            batch = Batch(batch_name="2035–39", start_year=2035, end_year=2039)
            db.add(batch)
            db.commit()
            with pytest.raises(HTTPException, match="At least one batch must remain"):
                MasterDataService(db).delete_batch(batch.id)
            assert db.query(Batch).count() == 1
    finally:
        engine.dispose()


def test_empty_section_can_be_deleted_without_affecting_other_sections(academic_db):
    db = academic_db["db"]
    batch, _ = academic_db["batches"]
    department = academic_db["department"]
    year = academic_db["years"][0]
    created = MasterDataService(db).create_section(SectionCreate(
        name="EMPTY",
        batch_id=batch.id,
        department_id=department.id,
        year_id=year.id,
    ))
    original_section_ids = {
        section.id for section in academic_db["sections"] if section.id != created.id
    }
    deletion_status = MasterDataService(db).get_section_deletion_status(created.id)
    assert deletion_status["can_delete"] is True
    assert deletion_status["reason"] is None
    assert deletion_status["student_count"] == 0
    assert deletion_status["placement_count"] == 0
    assert deletion_status["student_ids_to_delete"] == []
    assert deletion_status["student_ids_preserved"] == []
    assert len(deletion_status["plan_token"]) == 64
    assert MasterDataService(db).delete_section(created.id, deletion_status["plan_token"])
    assert db.query(Section).filter(Section.id == created.id).one_or_none() is None
    assert {row.id for row in db.query(Section).all()} == original_section_ids


def test_populated_section_delete_removes_only_its_owned_data(academic_db):
    db = academic_db["db"]
    batch, other_batch = academic_db["batches"]
    department = academic_db["department"]
    year = academic_db["years"][1]
    semester = academic_db["semesters"][2]
    section, other_section, foreign_section = academic_db["sections"]
    exam, foreign_exam = academic_db["exams"]
    target_subject, foreign_subject, other_year_subject = academic_db["subjects"]
    student = _add_deletion_test_student(db, batch, section, exam, "TEST-REG-0302")
    other_student = _add_deletion_test_student(
        db, other_batch, foreign_section, foreign_exam, "TEST-REG-0302"
    )
    original_placement = db.query(StudentAcademicPlacement).filter(
        StudentAcademicPlacement.student_id == student.id
    ).one()
    original_placement.is_current = False
    other_year_placement = StudentAcademicPlacement(
        student_id=student.id,
        batch_id=batch.id,
        department_id=department.id,
        year_id=year.id,
        semester_id=semester.id,
        section_id=other_section.id,
        is_current=True,
    )
    other_year_exam = Exam(
        name="Other year exam",
        exam_type="INTERNAL_1",
        batch=batch,
        department=department,
        year=year,
        semester=semester,
        section=other_section,
        subject=other_year_subject,
        pass_percentage=40,
    )
    db.add_all([other_year_placement, other_year_exam])
    db.flush()
    db.add_all([
        ExamQuestion(
            exam_id=other_year_exam.id,
            question_number="Q1",
            max_marks=10,
            co_code="CO1",
        ),
        StudentMark(
            exam_id=other_year_exam.id,
            student_id=student.id,
            question_number="Q1",
            obtained_mark=6,
        ),
    ])
    global_mapping = CourseCOPOMapping(
        subject_id=target_subject.id,
        section_id=None,
        mapping_data={"CO1": {"PO1": 2}},
    )
    db.add(global_mapping)
    db.commit()

    deletion_status = MasterDataService(db).get_section_deletion_status(section.id)
    assert deletion_status["student_count"] == 0
    assert deletion_status["placement_count"] == 1
    assert deletion_status["student_mark_count"] == 1
    assert deletion_status["exam_count"] == 1
    assert deletion_status["exam_question_count"] == 1
    assert deletion_status["exam_covered_co_count"] == 1
    assert deletion_status["student_ids_to_delete"] == []
    assert deletion_status["student_ids_preserved"] == [student.id]

    result = MasterDataService(db).delete_section(section.id, deletion_status["plan_token"])

    assert result == {
        "deleted_id": section.id,
        "message": "Section 'A' permanently deleted.",
    }
    assert db.query(Section).filter(Section.id == section.id).count() == 0
    db.refresh(student)
    assert student.register_no == "TEST-REG-0302"
    assert student.name == "Student TEST-REG-0302"
    assert student.batch_id == batch.id
    assert student.section_id is None
    assert db.query(StudentMark).filter(
        StudentMark.exam_id == exam.id,
        StudentMark.student_id == student.id,
    ).count() == 0
    db.refresh(other_year_placement)
    assert db.query(StudentAcademicPlacement).filter(
        StudentAcademicPlacement.id == original_placement.id
    ).one_or_none() is None
    assert other_year_placement.section_id == other_section.id
    assert other_year_placement.is_current is True
    assert db.query(Exam).filter(Exam.id == exam.id).count() == 0
    assert db.query(ExamQuestion).filter(ExamQuestion.exam_id == exam.id).count() == 0
    assert db.query(ExamCoveredCO).filter(ExamCoveredCO.exam_id == exam.id).count() == 0
    assert db.query(StudentMark).filter(StudentMark.exam_id == exam.id).count() == 0
    assert db.query(Exam).filter(Exam.id == other_year_exam.id).one_or_none() is other_year_exam
    assert db.query(ExamQuestion).filter(
        ExamQuestion.exam_id == other_year_exam.id
    ).count() == 1
    assert db.query(StudentMark).filter(
        StudentMark.exam_id == other_year_exam.id,
        StudentMark.student_id == student.id,
    ).count() == 1
    assert db.query(CourseCOPOMapping).filter(
        CourseCOPOMapping.section_id == section.id
    ).count() == 0
    assert db.query(CourseCOAttainmentInputs).filter(
        CourseCOAttainmentInputs.section_id == section.id
    ).count() == 0
    assert db.query(CourseCOPOMapping).filter(
        CourseCOPOMapping.id == global_mapping.id
    ).one_or_none() is global_mapping
    assert db.query(Batch).filter(Batch.id == batch.id).one_or_none() is batch
    assert db.query(Section).filter(Section.id == other_section.id).one_or_none() is other_section
    assert db.query(Student).filter(Student.id == other_student.id).one_or_none() is other_student
    assert db.query(StudentMark).filter(StudentMark.student_id == other_student.id).count() == 1
    assert db.query(Exam).filter(Exam.id == foreign_exam.id).one_or_none() is foreign_exam
    assert db.query(Subject).filter(Subject.id == target_subject.id).one_or_none() is target_subject
    assert db.query(Subject).filter(Subject.id == foreign_subject.id).one_or_none() is foreign_subject


def test_batch_delete_rolls_back_all_rows_when_a_dependent_delete_fails(academic_db):
    db = academic_db["db"]
    batch = academic_db["batches"][0]
    section = academic_db["sections"][0]
    exam = academic_db["exams"][0]
    student = _add_deletion_test_student(db, batch, section, exam, "TEST-REG-ROLLBACK")
    connection = db.get_bind()

    def fail_exam_delete(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("DELETE FROM EXAMS"):
            raise RuntimeError("injected dependent-delete failure")

    event.listen(connection, "before_cursor_execute", fail_exam_delete)
    try:
        with pytest.raises(RuntimeError, match="injected dependent-delete failure"):
            MasterDataService(db).delete_batch(batch.id)
    finally:
        event.remove(connection, "before_cursor_execute", fail_exam_delete)

    db.expire_all()
    assert db.query(Batch).filter(Batch.id == batch.id).one_or_none() is not None
    assert db.query(Student).filter(Student.id == student.id).one_or_none() is not None
    assert db.query(StudentMark).filter(StudentMark.student_id == student.id).count() == 1
    assert db.query(StudentAcademicPlacement).filter(
        StudentAcademicPlacement.student_id == student.id
    ).count() == 1
    assert db.query(ExamQuestion).filter(ExamQuestion.exam_id == exam.id).count() == 1
    assert db.query(ExamCoveredCO).filter(ExamCoveredCO.exam_id == exam.id).count() == 1
    assert db.query(CourseCOPOMapping).filter(
        CourseCOPOMapping.section_id == section.id
    ).count() == 1
    assert db.query(CourseCOAttainmentInputs).filter(
        CourseCOAttainmentInputs.section_id == section.id
    ).count() == 1
    assert db.query(Exam).filter(Exam.id == exam.id).one_or_none() is not None


def test_section_delete_rolls_back_all_rows_when_a_dependent_delete_fails(academic_db):
    db = academic_db["db"]
    batch = academic_db["batches"][0]
    section = academic_db["sections"][0]
    exam = academic_db["exams"][0]
    student = _add_deletion_test_student(db, batch, section, exam, "TEST-REG-SECTIONROLLBACK")
    deletion_status = MasterDataService(db).get_section_deletion_status(section.id)
    connection = db.get_bind()

    def fail_section_delete(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("DELETE FROM EXAMS"):
            raise RuntimeError("injected dependent-delete failure")

    event.listen(connection, "before_cursor_execute", fail_section_delete)
    try:
        with pytest.raises(RuntimeError, match="injected dependent-delete failure"):
            MasterDataService(db).delete_section(section.id, deletion_status["plan_token"])
    finally:
        event.remove(connection, "before_cursor_execute", fail_section_delete)

    db.expire_all()
    assert db.query(Section).filter(Section.id == section.id).one_or_none() is not None
    assert db.query(Student).filter(Student.id == student.id).one_or_none() is not None
    assert db.query(StudentMark).filter(StudentMark.student_id == student.id).count() == 1
    assert db.query(StudentAcademicPlacement).filter(
        StudentAcademicPlacement.student_id == student.id
    ).count() == 1
    assert db.query(Student).filter(
        Student.id == student.id,
        Student.section_id == section.id,
    ).count() == 1
    assert db.query(StudentAcademicPlacement).filter(
        StudentAcademicPlacement.student_id == student.id,
        StudentAcademicPlacement.section_id == section.id,
    ).count() == 1
    assert db.query(ExamQuestion).filter(ExamQuestion.exam_id == exam.id).count() == 1
    assert db.query(ExamCoveredCO).filter(ExamCoveredCO.exam_id == exam.id).count() == 1
    assert db.query(CourseCOPOMapping).filter(
        CourseCOPOMapping.section_id == section.id
    ).count() == 1
    assert db.query(CourseCOAttainmentInputs).filter(
        CourseCOAttainmentInputs.section_id == section.id
    ).count() == 1
    assert db.query(Exam).filter(Exam.id == exam.id).one_or_none() is not None


def test_section_add_and_duplicate_validation(academic_db):
    db = academic_db["db"]
    batch = academic_db["batches"][0]
    department = academic_db["department"]
    year = academic_db["years"][0]
    payload = SectionCreate(
        name="C",
        batch_id=batch.id,
        department_id=department.id,
        year_id=year.id,
    )
    created = MasterDataService(db).create_section(payload)
    assert created.name == "C"
    assert created.batch_id == batch.id
    with pytest.raises(HTTPException, match="already exists"):
        MasterDataService(db).create_section(payload)
    assert db.query(Section).filter(
        Section.batch_id == batch.id,
        Section.department_id == department.id,
        Section.year_id == year.id,
        Section.name == "C",
    ).count() == 1


def test_batch_delete_endpoint_succeeds_for_empty_batch(academic_db, academic_api_client):
    db = academic_db["db"]
    batch = MasterDataService(db).create_batch(BatchCreate(
        batch_name="2040–44",
        start_year=2040,
        end_year=2044,
    ))

    response = academic_api_client.delete(f"/api/academic/batches/{batch.id}")

    assert response.status_code == 200
    assert response.json() == {
        "deleted_id": batch.id,
        "message": f"Batch '{batch.batch_name}' permanently deleted.",
    }
    assert db.query(Batch).filter(Batch.id == batch.id).one_or_none() is None


def test_batch_delete_endpoint_deletes_populated_batch(academic_db, academic_api_client):
    batch = academic_db["batches"][0]
    section = academic_db["sections"][0]
    exam = academic_db["exams"][0]
    student = _add_deletion_test_student(
        academic_db["db"], batch, section, exam, "TEST-REG-APIDELETE"
    )

    response = academic_api_client.delete(f"/api/academic/batches/{batch.id}")

    assert response.status_code == 200
    assert response.json()["deleted_id"] == batch.id
    assert academic_db["db"].query(Batch).filter(Batch.id == batch.id).one_or_none() is None
    assert academic_db["db"].query(Student).filter(Student.id == student.id).count() == 0


def test_batch_delete_endpoint_returns_404_for_invalid_id(academic_api_client):
    response = academic_api_client.delete("/api/academic/batches/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Batch not found"


def test_section_delete_endpoint_succeeds_for_empty_section(academic_db, academic_api_client):
    db = academic_db["db"]
    created = MasterDataService(db).create_section(SectionCreate(
        name="EMPTY-API",
        batch_id=academic_db["batches"][0].id,
        department_id=academic_db["department"].id,
        year_id=academic_db["years"][0].id,
    ))

    preview = academic_api_client.get(
        f"/api/academic/sections/{created.id}/deletion-status"
    )
    assert preview.status_code == 200, preview.text
    response = academic_api_client.delete(
        f"/api/academic/sections/{created.id}",
        params={"plan_token": preview.json()["plan_token"]},
    )

    assert response.status_code == 200
    assert response.json()["deleted_id"] == created.id
    assert db.query(Section).filter(Section.id == created.id).one_or_none() is None


def test_section_delete_endpoint_deletes_populated_section(academic_db, academic_api_client):
    db = academic_db["db"]
    section = academic_db["sections"][0]
    student = _add_deletion_test_student(
        db,
        academic_db["batches"][0],
        section,
        academic_db["exams"][0],
        "TEST-REG-APISECTIONDELETE",
    )

    preview = academic_api_client.get(
        f"/api/academic/sections/{section.id}/deletion-status"
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["student_count"] == 1
    assert preview.json()["placement_count"] == 1
    assert preview.json()["student_mark_count"] == 1
    assert preview.json()["student_ids_to_delete"] == [student.id]
    assert len(preview.json()["plan_token"]) == 64

    response = academic_api_client.delete(
        f"/api/academic/sections/{section.id}",
        params={"plan_token": preview.json()["plan_token"]},
    )

    assert response.status_code == 200
    assert response.json()["deleted_id"] == section.id
    assert db.query(Section).filter(Section.id == section.id).one_or_none() is None
    assert db.query(Student).filter(Student.id == student.id).one_or_none() is None
    assert db.query(StudentAcademicPlacement).filter(
        StudentAcademicPlacement.student_id == student.id
    ).count() == 0
    assert db.query(StudentMark).filter(StudentMark.student_id == student.id).count() == 0


def test_section_delete_rejects_a_stale_deletion_preview(academic_db, academic_api_client):
    db = academic_db["db"]
    section = academic_db["sections"][0]
    batch = academic_db["batches"][0]
    exam = academic_db["exams"][0]
    first_student = _add_deletion_test_student(
        db, batch, section, exam, "TEST-REG-STALEPREVIEW1"
    )
    preview = academic_api_client.get(
        f"/api/academic/sections/{section.id}/deletion-status"
    )
    assert preview.status_code == 200, preview.text

    second_student = Student(
        register_no="TEST-REG-STALEPREVIEW2",
        name="Student TEST-REG-STALEPREVIEW2",
        batch_id=batch.id,
        section_id=section.id,
    )
    db.add(second_student)
    db.flush()
    db.add(StudentAcademicPlacement(
        student_id=second_student.id,
        batch_id=batch.id,
        department_id=section.department_id,
        year_id=section.year_id,
        semester_id=exam.semester_id,
        section_id=section.id,
        is_current=True,
    ))
    db.commit()
    response = academic_api_client.delete(
        f"/api/academic/sections/{section.id}",
        params={"plan_token": preview.json()["plan_token"]},
    )

    assert response.status_code == 409
    assert "changed after the deletion preview" in response.json()["detail"]
    assert db.query(Section).filter(Section.id == section.id).one_or_none() is not None
    assert db.query(Student).filter(Student.id == first_student.id).one_or_none() is not None
    assert db.query(StudentMark).filter(
        StudentMark.student_id == first_student.id
    ).count() == 1


def test_section_delete_and_same_roster_import_preserve_other_section_students(
    academic_db,
    academic_api_client,
):
    db = academic_db["db"]
    batch = academic_db["batches"][0]
    department = academic_db["department"]
    section, other_section = academic_db["sections"][:2]
    exam = academic_db["exams"][0]
    removed_student = _add_deletion_test_student(
        db, batch, section, exam, "SECTION-REIMPORT-001"
    )

    preserved_student_ids = []
    blocker_students = []
    for index in range(59):
        student = Student(
            register_no=f"RESTORED-UNCHANGED-{index:02d}",
            name=f"Restored Student {index:02d}",
            batch_id=batch.id,
            section_id=other_section.id,
        )
        db.add(student)
        db.flush()
        db.add(StudentAcademicPlacement(
            student_id=student.id,
            batch_id=batch.id,
            department_id=department.id,
            year_id=other_section.year_id,
            section_id=other_section.id,
            section_name=other_section.name,
            is_current=True,
        ))
        preserved_student_ids.append(student.id)

    blocker_registers = ["BLOCKED-ROW-12", "BLOCKED-ROW-33", "BLOCKED-ROW-34", "BLOCKED-ROW-35", "BLOCKED-ROW-36"]
    for register_no in blocker_registers:
        student = Student(
            register_no=register_no,
            name=f"Student {register_no}",
            batch_id=batch.id,
            section_id=other_section.id,
        )
        db.add(student)
        db.flush()
        db.add(StudentAcademicPlacement(
            student_id=student.id,
            batch_id=batch.id,
            department_id=department.id,
            year_id=other_section.year_id,
            section_id=other_section.id,
            section_name=other_section.name,
            is_current=True,
        ))
        blocker_students.append(student.id)
    db.commit()
    preserved_student_snapshot = [
        (
            student.id,
            student.register_no,
            student.name,
            student.batch_id,
            student.section_id,
            student.archived_at,
            student.created_at,
            student.updated_at,
        )
        for student in db.query(Student)
        .filter(Student.id.in_(preserved_student_ids))
        .order_by(Student.id)
        .all()
    ]
    preserved_placement_snapshot = [
        (
            placement.id,
            placement.student_id,
            placement.batch_id,
            placement.department_id,
            placement.year_id,
            placement.semester_id,
            placement.section_id,
            placement.section_name,
            placement.is_current,
            placement.effective_from,
            placement.effective_to,
            placement.created_at,
        )
        for placement in db.query(StudentAcademicPlacement)
        .filter(StudentAcademicPlacement.student_id.in_(preserved_student_ids))
        .order_by(StudentAcademicPlacement.id)
        .all()
    ]

    preview = academic_api_client.get(
        f"/api/academic/sections/{section.id}/deletion-status"
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["student_ids_to_delete"] == [removed_student.id]
    assert preview.json()["student_ids_preserved"] == []
    deleted = academic_api_client.delete(
        f"/api/academic/sections/{section.id}",
        params={"plan_token": preview.json()["plan_token"]},
    )
    assert deleted.status_code == 200, deleted.text

    replacement_section = MasterDataService(db).create_section(SectionCreate(
        name=section.name,
        batch_id=batch.id,
        department_id=section.department_id,
        year_id=section.year_id,
    ))
    roster_rows = [
        ("SECTION-REIMPORT-001", "Student SECTION-REIMPORT-001"),
        *[(register_no, f"Student {register_no}") for register_no in blocker_registers],
    ]
    roster = "Register Number,Student Name\n" + "".join(
        f"{register_no},{name}\n" for register_no, name in roster_rows
    )
    roster_preview = academic_api_client.post(
        "/api/students/import-preview",
        files={"file": ("same-roster.csv", roster, "text/csv")},
        data={"section_id": str(replacement_section.id)},
    )
    assert roster_preview.status_code == 200, roster_preview.text
    assert roster_preview.json()["new_students"] == 1
    assert roster_preview.json()["placement_conflicts"] == 5
    resolutions = {
        item["register_no"]: item
        for item in roster_preview.json()["identity_resolutions"]
    }
    assert [resolutions[register_no]["selected_student_id"] for register_no in blocker_registers] == blocker_students

    imported = academic_api_client.post(
        "/api/students/import",
        files={"file": ("same-roster.csv", roster, "text/csv")},
        data={"section_id": str(replacement_section.id), "confirm": "true"},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported_count"] == 1
    assert imported.json()["skipped_conflict_count"] == 5
    recreated_student = db.query(Student).filter(
        Student.register_no == "SECTION-REIMPORT-001",
        Student.section_id == replacement_section.id,
    ).one()
    assert recreated_student.id != removed_student.id
    assert db.query(Student).filter(Student.id == removed_student.id).one_or_none() is None
    assert db.query(StudentMark).filter(
        StudentMark.student_id == removed_student.id
    ).count() == 0
    assert [
        (
            student.id,
            student.register_no,
            student.name,
            student.batch_id,
            student.section_id,
            student.archived_at,
            student.created_at,
            student.updated_at,
        )
        for student in db.query(Student).filter(
            Student.id.in_(preserved_student_ids)
        ).order_by(Student.id)
    ] == preserved_student_snapshot
    assert [
        (
            placement.id,
            placement.student_id,
            placement.batch_id,
            placement.department_id,
            placement.year_id,
            placement.semester_id,
            placement.section_id,
            placement.section_name,
            placement.is_current,
            placement.effective_from,
            placement.effective_to,
            placement.created_at,
        )
        for placement in db.query(StudentAcademicPlacement)
        .filter(StudentAcademicPlacement.student_id.in_(preserved_student_ids))
        .order_by(StudentAcademicPlacement.id)
        .all()
    ] == preserved_placement_snapshot
    assert db.query(Student).filter(Student.id.in_(blocker_students)).count() == 5
    assert db.query(StudentAcademicPlacement).filter(
        StudentAcademicPlacement.student_id.in_(blocker_students),
        StudentAcademicPlacement.is_current.is_(True),
        StudentAcademicPlacement.section_id == other_section.id,
    ).count() == 5
    assert db.connection().exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []


def test_section_delete_endpoint_returns_404_for_invalid_id(academic_api_client):
    response = academic_api_client.delete(
        "/api/academic/sections/999999",
        params={"plan_token": "0" * 64},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Section not found"
