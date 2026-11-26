"""
Phase 4 Automated Test Suite:
Validates:
1. PostgreSQL Database Models & Constraints
2. User Authentication and 4 Roles (Admin, Faculty, Class Advisor, HOD)
3. Bcrypt Password Hashing & JWT Bearer Tokens
4. Academic Hierarchy: Department -> Year -> Semester -> Section -> Students
5. Student management (Belongs to Section, NOT Subject)
6. Subject management (Subject Name only, independent of Students)
7. API endpoints across Auth and Master Data
"""

import os
import pytest
import importlib.util
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.base import Base
from app.db.models import Batch, User, UserRole, Department, Year, Semester, Section, Student, Subject, Exam
from app.db.session import SessionLocal, get_db
from app.main import app
from app.seeds.dev_seed import seed_database
from app.security.auth import hash_password, verify_password, create_access_token, decode_access_token

client = TestClient(app)
EXPECTED_DEPARTMENTS = {"CSE", "IT", "ECE", "AIML", "IOT", "EEE", "RA", "MECH", "FT"}


def _subjects_url(department_id=1, year_id=3, semester_id=5, section_id=None):
    params = f"department_id={department_id}&year_id={year_id}&semester_id={semester_id}"
    if section_id is not None:
        params += f"&section_id={section_id}"
    return f"/api/subjects?{params}"


def test_section_migration_preserves_student_exam_and_mark_references(tmp_path):
    database = create_engine(f"sqlite:///{tmp_path / 'legacy.sqlite'}")
    with database.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE departments (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE years (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE semesters (id INTEGER PRIMARY KEY, year_id INTEGER NOT NULL)")
        connection.exec_driver_sql(
            "CREATE TABLE sections ("
            "id INTEGER PRIMARY KEY, name VARCHAR(20) NOT NULL, department_id INTEGER NOT NULL, "
            "year_id INTEGER NOT NULL, semester_id INTEGER NOT NULL, "
            "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "CONSTRAINT uq_dept_year_sem_section UNIQUE (department_id, year_id, semester_id, name), "
            "FOREIGN KEY(department_id) REFERENCES departments(id), "
            "FOREIGN KEY(year_id) REFERENCES years(id), "
            "FOREIGN KEY(semester_id) REFERENCES semesters(id))"
        )
        connection.exec_driver_sql("CREATE INDEX idx_section_lookup ON sections (department_id, year_id, semester_id)")
        connection.exec_driver_sql(
            "CREATE TABLE students (id INTEGER PRIMARY KEY, section_id INTEGER NOT NULL REFERENCES sections(id))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE exams (id INTEGER PRIMARY KEY, department_id INTEGER NOT NULL, year_id INTEGER NOT NULL, "
            "semester_id INTEGER NOT NULL, section_id INTEGER NOT NULL REFERENCES sections(id), "
            "subject_id INTEGER NOT NULL, name VARCHAR(100) NOT NULL, "
            "CONSTRAINT uq_exam_class_subject_name UNIQUE "
            "(department_id, year_id, semester_id, section_id, subject_id, name))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE student_marks (id INTEGER PRIMARY KEY, exam_id INTEGER NOT NULL, student_id INTEGER NOT NULL)"
        )
        connection.exec_driver_sql("INSERT INTO departments (id) VALUES (1)")
        connection.exec_driver_sql("INSERT INTO years (id) VALUES (3)")
        connection.exec_driver_sql("INSERT INTO semesters (id, year_id) VALUES (5, 3), (6, 3)")
        connection.exec_driver_sql(
            "INSERT INTO sections (id, name, department_id, year_id, semester_id) "
            "VALUES (101, 'A', 1, 3, 5), (102, 'A', 1, 3, 6)"
        )
        connection.exec_driver_sql("INSERT INTO students (id, section_id) VALUES (501, 101), (502, 102)")
        connection.exec_driver_sql(
            "INSERT INTO exams (id, department_id, year_id, semester_id, section_id, subject_id, name) "
            "VALUES (601, 1, 3, 5, 101, 1, 'Exam'), (602, 1, 3, 6, 102, 1, 'Exam')"
        )
        connection.exec_driver_sql(
            "INSERT INTO student_marks (id, exam_id, student_id) VALUES (701, 601, 501), (702, 602, 502)"
        )

    migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "004_section_by_department_year.py"
    spec = importlib.util.spec_from_file_location("section_by_department_year", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with database.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    with database.connect() as connection:
        columns = {row["name"] for row in connection.execute(text("PRAGMA table_info(sections)")).mappings()}
        assert "semester_id" not in columns
        assert connection.execute(text("SELECT id FROM sections")).scalars().all() == [101]
        assert connection.execute(text("SELECT id, section_id FROM students ORDER BY id")).all() == [
            (501, 101), (502, 101)
        ]
        assert connection.execute(text("SELECT id, semester_id, section_id FROM exams ORDER BY id")).all() == [
            (601, 5, 101), (602, 6, 101)
        ]
        assert connection.execute(text("SELECT id, exam_id, student_id FROM student_marks ORDER BY id")).all() == [
            (701, 601, 501), (702, 602, 502)
        ]
        with pytest.raises(IntegrityError):
            connection.execute(
                text("INSERT INTO sections (id, name, department_id, year_id) VALUES (103, 'A', 1, 3)")
            )
    database.dispose()


def test_numeric_roll_number_migration_preserves_other_student_data(tmp_path):
    database = create_engine(f"sqlite:///{tmp_path / 'roll_numbers.sqlite'}")
    with database.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE departments (id INTEGER PRIMARY KEY, code VARCHAR(20))")
        connection.exec_driver_sql("CREATE TABLE years (id INTEGER PRIMARY KEY, year_number INTEGER)")
        connection.exec_driver_sql(
            "CREATE TABLE sections (id INTEGER PRIMARY KEY, name VARCHAR(20), department_id INTEGER, year_id INTEGER)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE students (id INTEGER PRIMARY KEY, register_no VARCHAR(50), name VARCHAR(100), section_id INTEGER)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE student_marks (id INTEGER PRIMARY KEY, student_id INTEGER, obtained_mark NUMERIC)"
        )
        connection.exec_driver_sql("INSERT INTO departments VALUES (1, 'CSE'), (2, 'IT')")
        connection.exec_driver_sql("INSERT INTO years VALUES (2, 2), (3, 3)")
        connection.exec_driver_sql(
            "INSERT INTO sections VALUES (11, 'A', 1, 3), (12, 'B', 1, 3), (13, 'A', 1, 2), (14, 'A', 2, 3)"
        )
        connection.exec_driver_sql(
            "INSERT INTO students VALUES "
            "(1, '1', 'ROLL ONE', 11), (2, '2', 'ROLL TWO', 11), "
            "(3, '101', 'ROLL 101', 12), (4, 'TEST-REG-0349', 'EXISTING CODE', 11), "
            "(5, '1', 'OTHER YEAR', 13), (6, '1', 'OTHER DEPARTMENT', 14)"
        )
        connection.exec_driver_sql("INSERT INTO student_marks VALUES (21, 1, 8.5), (22, 3, 9.0)")

    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "009_normalize_numeric_student_register_numbers.py"
    )
    spec = importlib.util.spec_from_file_location("normalize_numeric_student_register_numbers", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with database.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    with database.connect() as connection:
        assert connection.execute(text("SELECT id, register_no, name, section_id FROM students ORDER BY id")).all() == [
            (1, "24TD0301", "ROLL ONE", 11),
            (2, "24TD0302", "ROLL TWO", 11),
            (3, "24TD0401", "ROLL 101", 12),
            (4, "TEST-REG-0349", "EXISTING CODE", 11),
            (5, "1", "OTHER YEAR", 13),
            (6, "1", "OTHER DEPARTMENT", 14),
        ]
        assert connection.execute(text("SELECT id, student_id, obtained_mark FROM student_marks ORDER BY id")).all() == [
            (21, 1, 8.5),
            (22, 3, 9),
        ]
    database.dispose()


def test_subject_archive_migration_preserves_existing_subjects(tmp_path):
    database = create_engine(f"sqlite:///{tmp_path / 'subject_archive.sqlite'}")
    with database.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE subjects (id INTEGER PRIMARY KEY, name VARCHAR(150) NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO subjects (id, name) VALUES (1, 'EXISTING SUBJECT'), (2, 'ANOTHER SUBJECT')"
        )

    migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "010_subject_archive.py"
    spec = importlib.util.spec_from_file_location("subject_archive", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with database.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    with database.connect() as connection:
        assert connection.execute(
            text("SELECT id, name, is_active FROM subjects ORDER BY id")
        ).all() == [(1, "EXISTING SUBJECT", 1), (2, "ANOTHER SUBJECT", 1)]
    database.dispose()


def test_subject_scope_migration_preserves_exam_contexts_and_reports_unknowns(tmp_path, capsys):
    database = create_engine(f"sqlite:///{tmp_path / 'legacy_subjects.sqlite'}")
    with database.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE departments (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, code VARCHAR(20) NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE years (id INTEGER PRIMARY KEY, year_number INTEGER NOT NULL, name VARCHAR(20) NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE semesters (id INTEGER PRIMARY KEY, semester_number INTEGER NOT NULL, "
            "name VARCHAR(20) NOT NULL, year_id INTEGER NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE subjects (id INTEGER PRIMARY KEY, name VARCHAR(150) NOT NULL, "
            "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        connection.exec_driver_sql("CREATE UNIQUE INDEX ix_subjects_name ON subjects (name)")
        connection.exec_driver_sql(
            "CREATE TABLE exams (id INTEGER PRIMARY KEY, name VARCHAR(100), department_id INTEGER, "
            "year_id INTEGER, semester_id INTEGER, subject_id INTEGER)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE exam_questions (id INTEGER PRIMARY KEY, exam_id INTEGER, question_number VARCHAR(20))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE student_marks (id INTEGER PRIMARY KEY, exam_id INTEGER, student_id INTEGER, "
            "question_number VARCHAR(20), obtained_mark NUMERIC)"
        )
        connection.exec_driver_sql(
            "INSERT INTO subjects (id, name) VALUES "
            "(1, 'DATABASE MANAGEMENT SYSTEMS'), (2, 'THEORY OF COMPUTATION'), "
            "(3, 'COMPUTER NETWORKS'), (4, 'OPERATING SYSTEM'), "
            "(5, 'SOFTWARE ENGINEERING'), (6, 'UNMAPPED LEGACY SUBJECT')"
        )
        connection.exec_driver_sql(
            "INSERT INTO exams (id, name, department_id, year_id, semester_id, subject_id) VALUES "
            "(101, 'Y1 Exam', 1, 1, 1, 1), (102, 'Y3 Exam 1', 1, 3, 6, 1), "
            "(103, 'Y3 Exam 2', 1, 3, 6, 1), (104, 'Y3 Exam 3', 1, 3, 6, 1), "
            "(105, 'Legacy ToC Exam', 1, 3, 6, 2)"
        )
        connection.exec_driver_sql("INSERT INTO exam_questions (id, exam_id, question_number) VALUES (201, 101, 'Q1')")
        connection.exec_driver_sql(
            "INSERT INTO student_marks (id, exam_id, student_id, question_number, obtained_mark) "
            "VALUES (301, 101, 401, 'Q1', 5)"
        )

    migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "005_subject_academic_scope.py"
    spec = importlib.util.spec_from_file_location("subject_academic_scope", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with database.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    with database.connect() as connection:
        exam_rows = connection.execute(
            text("SELECT id, semester_id, subject_id FROM exams ORDER BY id")
        ).all()
        assert [row[0] for row in exam_rows] == [101, 102, 103, 104, 105]
        assert exam_rows[0][2] != exam_rows[1][2]
        assert exam_rows[1][2] == exam_rows[2][2] == exam_rows[3][2]
        assert exam_rows[4][1] == 6

        context_rows = connection.execute(text(
            "SELECT id, name, department_id, year_id, semester_id FROM subjects ORDER BY id"
        )).all()
        subject_by_id = {row[0]: row for row in context_rows}
        assert subject_by_id[1][2:] == (1, 3, 6)
        assert subject_by_id[3][2:] == (1, 3, 5)
        assert subject_by_id[4][2:] == (1, 3, 5)
        assert subject_by_id[5][2:] == (1, 3, 5)
        assert subject_by_id[6][2:] == (None, None, None)
        assert any(row[1] == "DATABASE SYSTEM" and row[4] == 5 for row in context_rows)
        assert any(row[1] == "THEORY OF COMPUTATION" and row[4] == 5 for row in context_rows)
        assert any(row[1] == "WEB TECHNOLOGIES" and row[4] == 6 for row in context_rows)
        semester_5_names = {
            row[1] for row in context_rows if row[2:] == (1, 3, 5)
        }
        semester_6_names = {
            row[1]
            for row in context_rows
            if row[2:] == (1, 3, 6) and row[1] in set(migration.CURRICULUM[6])
        }
        assert semester_5_names == set(migration.CURRICULUM[5])
        assert semester_6_names == set(migration.CURRICULUM[6])
        assert connection.execute(text("SELECT * FROM exam_questions")).all() == [(201, 101, "Q1")]
        assert connection.execute(text("SELECT * FROM student_marks")).all() == [
            (301, 101, 401, "Q1", 5)
        ]

    assert "UNMAPPED LEGACY SUBJECT" in capsys.readouterr().out
    database.dispose()


def test_subject_scope_reference_data_is_idempotent_and_rejects_conflicts(tmp_path):
    database = create_engine(f"sqlite:///{tmp_path / 'academic_references.sqlite'}")
    with database.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE departments (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, code VARCHAR(20) NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE years (id INTEGER PRIMARY KEY, year_number INTEGER NOT NULL, name VARCHAR(20) NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE semesters (id INTEGER PRIMARY KEY, semester_number INTEGER NOT NULL, "
            "name VARCHAR(20) NOT NULL, year_id INTEGER NOT NULL)"
        )

    migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "005_subject_academic_scope.py"
    spec = importlib.util.spec_from_file_location("subject_academic_scope_references", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    with database.begin() as connection:
        migration._ensure_academic_reference_data(connection)
        original_ids = {
            "departments": connection.execute(text("SELECT code, id FROM departments ORDER BY code")).all(),
            "years": connection.execute(text("SELECT year_number, id FROM years ORDER BY year_number")).all(),
            "semesters": connection.execute(text("SELECT semester_number, id FROM semesters ORDER BY semester_number")).all(),
        }
        migration._ensure_academic_reference_data(connection)
        assert connection.execute(text("SELECT COUNT(*) FROM departments")).scalar_one() == 9
        assert connection.execute(text("SELECT COUNT(*) FROM years")).scalar_one() == 4
        assert connection.execute(text("SELECT COUNT(*) FROM semesters")).scalar_one() == 8
        assert {
            "departments": connection.execute(text("SELECT code, id FROM departments ORDER BY code")).all(),
            "years": connection.execute(text("SELECT year_number, id FROM years ORDER BY year_number")).all(),
            "semesters": connection.execute(text("SELECT semester_number, id FROM semesters ORDER BY semester_number")).all(),
        } == original_ids

        year_ids = dict(connection.execute(text("SELECT year_number, id FROM years")).all())
        assert connection.execute(
            text("SELECT semester_number, year_id FROM semesters ORDER BY semester_number")
        ).all() == [
            (number, year_ids[(number + 1) // 2])
            for number in range(1, 9)
        ]

        connection.execute(
            text("UPDATE semesters SET year_id = :year_id WHERE semester_number = 5"),
            {"year_id": year_ids[2]},
        )
        with pytest.raises(RuntimeError, match="Conflicting academic semester mapping for Semester 5"):
            migration._ensure_academic_reference_data(connection)
        assert connection.execute(
            text("SELECT year_id FROM semesters WHERE semester_number = 5")
        ).scalar_one() == year_ids[2]
    database.dispose()


@pytest.mark.parametrize(
    ("dialect_name", "expected_operations"),
    [
        ("postgresql", ["alter_column", "execute"]),
        ("sqlite", ["execute"]),
    ],
)
def test_cse_subject_correction_migration_expands_postgresql_revision_column(
    monkeypatch, dialect_name, expected_operations
):
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "006_correct_cse_year3_semester6_subjects.py"
    )
    spec = importlib.util.spec_from_file_location(
        "correct_cse_year3_semester6_subjects", migration_path
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    operations = []

    class Bind:
        def __init__(self, name):
            self.dialect = type("Dialect", (), {"name": name})()

        def execute(self, *args):
            operations.append(("execute", args))

    monkeypatch.setattr(migration.op, "get_bind", lambda: Bind(dialect_name))
    monkeypatch.setattr(
        migration.op,
        "alter_column",
        lambda *args, **kwargs: operations.append(("alter_column", args, kwargs)),
    )

    migration.upgrade()

    assert [operation[0] for operation in operations] == expected_operations
    if dialect_name == "postgresql":
        _, args, kwargs = operations[0]
        assert args == ("alembic_version", "version_num")
        assert kwargs["existing_type"].length == 32
        assert kwargs["type_"].length == 255


# ---------------- 1. Security & Hashing Unit Tests ----------------
def test_password_hashing_and_verification():
    raw_pw = "Secret@123"
    hashed = hash_password(raw_pw)
    assert hashed != raw_pw
    assert hashed.startswith("$2b$")
    assert verify_password(raw_pw, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_jwt_token_generation_and_decoding():
    token = create_access_token(username="test_admin", role=UserRole.ADMIN)
    payload = decode_access_token(token)
    assert payload is not None
    assert payload.sub == "test_admin"
    assert payload.role == UserRole.ADMIN


# ---------------- 2. Authentication API Tests ----------------
def test_login_success_and_role_confirmation():
    # Login with seeded admin
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": os.environ["OBE_SEED_ADMIN_PASSWORD"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["username"] == "admin"
    assert data["role"] == "ADMIN"


def test_all_four_roles_can_authenticate():
    roles_credentials = [
        ("admin", os.environ["OBE_SEED_ADMIN_PASSWORD"], "ADMIN"),
        ("faculty1", os.environ["OBE_SEED_FACULTY_PASSWORD"], "FACULTY"),
        ("advisor1", os.environ["OBE_SEED_ADVISOR_PASSWORD"], "CLASS_ADVISOR"),
        ("hod_cse", os.environ["OBE_SEED_HOD_PASSWORD"], "HOD"),
    ]
    for username, pw, expected_role in roles_credentials:
        resp = client.post("/api/auth/login", json={"username": username, "password": pw})
        assert resp.status_code == 200, f"Failed login for {username}"
        data = resp.json()
        assert data["role"] == expected_role


def test_login_invalid_credentials():
    resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "WrongPassword"},
    )
    assert resp.status_code == 401
    assert "Incorrect username or password" in resp.json()["detail"]


def test_auth_profile_still_requires_bearer_token():
    # Authentication endpoints remain protected for future auth use.
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401

    # Attempt with valid token
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": os.environ["OBE_SEED_ADMIN_PASSWORD"]})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me_resp = client.get("/api/auth/me", headers=headers)
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["username"] == "admin"
    assert me_data["role"] == "ADMIN"


def test_obe_master_data_routes_are_usable_without_bearer_token():
    departments = client.get("/api/departments")
    years = client.get("/api/academic/years")
    subjects = client.get(_subjects_url())
    sections = client.get("/api/academic/sections")
    students = client.get("/api/students")

    assert departments.status_code == 200
    assert years.status_code == 200
    assert subjects.status_code == 200
    assert sections.status_code == 200
    assert students.status_code == 200


# ---------------- 3. Academic Structure Tests ----------------
def test_academic_years_and_semesters_hierarchy():
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": os.environ["OBE_SEED_ADMIN_PASSWORD"]})
    headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    # 4 Academic Years
    years_resp = client.get("/api/academic/years", headers=headers)
    assert years_resp.status_code == 200
    years = years_resp.json()
    assert len(years) == 4
    year_names = [y["name"] for y in years]
    assert "1st Year" in year_names
    assert "2nd Year" in year_names
    assert "3rd Year" in year_names
    assert "4th Year" in year_names

    # Semesters for 3rd Year
    year_3 = next(y for y in years if y["year_number"] == 3)
    sem_resp = client.get(f"/api/academic/semesters?year_id={year_3['id']}", headers=headers)
    assert sem_resp.status_code == 200
    semesters = sem_resp.json()
    assert len(semesters) == 2
    sem_numbers = [s["semester_number"] for s in semesters]
    assert 5 in sem_numbers
    assert 6 in sem_numbers


def test_sections_are_unique_by_department_and_year_without_semester():
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": os.environ["OBE_SEED_ADMIN_PASSWORD"]})
    headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}
    cse = next(d for d in client.get("/api/departments", headers=headers).json() if d["code"] == "CSE")
    year_3 = next(y for y in client.get("/api/academic/years", headers=headers).json() if y["year_number"] == 3)
    semesters = client.get(f"/api/academic/semesters?year_id={year_3['id']}", headers=headers).json()
    semester_5 = next(s for s in semesters if s["semester_number"] == 5)
    semester_6 = next(s for s in semesters if s["semester_number"] == 6)

    sections_5 = client.get(
        f"/api/academic/sections?department_id={cse['id']}&year_id={year_3['id']}&semester_id={semester_5['id']}",
        headers=headers,
    ).json()
    sections_6 = client.get(
        f"/api/academic/sections?department_id={cse['id']}&year_id={year_3['id']}&semester_id={semester_6['id']}",
        headers=headers,
    ).json()
    assert sections_5 == sections_6
    assert sum(section["name"] == "A" for section in sections_5) == 1
    assert all("semester_id" not in section for section in sections_5)

    duplicate = client.post(
        "/api/academic/sections",
        json={"name": "A", "department_id": cse["id"], "year_id": year_3["id"]},
        headers=headers,
    )
    assert duplicate.status_code == 400


def test_section_creation_and_uniqueness():
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": os.environ["OBE_SEED_ADMIN_PASSWORD"]})
    headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    dept_resp = client.get("/api/departments", headers=headers)
    dept_id = dept_resp.json()[0]["id"]
    years_resp = client.get("/api/academic/years", headers=headers)
    year_3 = next(y for y in years_resp.json() if y["year_number"] == 3)
    # Section B exists once for CSE 3rd Year, independent of semester.
    payload = {
        "name": "B",
        "department_id": dept_id,
        "year_id": year_3["id"],
    }
    resp = client.post("/api/academic/sections", json=payload, headers=headers)
    assert resp.status_code in (201, 400)  # 201 if first time, 400 if duplicate

    # Duplicate Section B must be rejected
    dup_resp = client.post("/api/academic/sections", json=payload, headers=headers)
    assert dup_resp.status_code == 400
    assert "already exists" in dup_resp.json()["detail"]


def test_dynamic_sections_can_be_added_and_populated_sections_removed():
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": os.environ["OBE_SEED_ADMIN_PASSWORD"]})
    headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}
    departments = client.get("/api/departments", headers=headers).json()
    cse = next(department for department in departments if department["code"] == "CSE")
    years = client.get("/api/academic/years", headers=headers).json()
    year_2 = next(year for year in years if year["year_number"] == 2)
    year_3 = next(year for year in years if year["year_number"] == 3)

    created = client.post(
        "/api/academic/sections",
        json={"name": "D", "department_id": cse["id"], "year_id": year_2["id"]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    sections = client.get(
        f"/api/academic/sections?department_id={cse['id']}&year_id={year_2['id']}",
        headers=headers,
    ).json()
    assert any(section["id"] == created.json()["id"] and section["name"] == "D" for section in sections)

    removed = client.delete(f"/api/academic/sections/{created.json()['id']}", headers=headers)
    assert removed.status_code == 200, removed.text
    assert removed.json()["deleted_id"] == created.json()["id"]
    assert "permanently deleted" in removed.json()["message"]
    sections_after_remove = client.get(
        f"/api/academic/sections?department_id={cse['id']}&year_id={year_2['id']}",
        headers=headers,
    ).json()
    assert all(section["name"] != "D" for section in sections_after_remove)

    populated_section = client.post(
        "/api/academic/sections",
        json={"name": "DELETE-TEST", "department_id": cse["id"], "year_id": year_2["id"]},
        headers=headers,
    )
    assert populated_section.status_code == 201, populated_section.text
    with SessionLocal() as db:
        batch = db.query(Batch).filter(Batch.start_year == 2024, Batch.end_year == 2028).one()
        batch_id = batch.id
        student = Student(
            register_no="TEST-DELETE-SECTION",
            name="Section Delete Test Student",
            batch_id=batch.id,
            section_id=populated_section.json()["id"],
        )
        db.add(student)
        db.commit()
        student_id = student.id

    populated_remove = client.delete(
        f"/api/academic/sections/{populated_section.json()['id']}",
        headers=headers,
    )
    assert populated_remove.status_code == 200, populated_remove.text
    assert populated_remove.json()["deleted_id"] == populated_section.json()["id"]
    with SessionLocal() as db:
        assert db.query(Section).filter(Section.id == populated_section.json()["id"]).one_or_none() is None
        preserved_student = db.query(Student).filter(Student.id == student_id).one()
        assert preserved_student.register_no == "TEST-DELETE-SECTION"
        assert preserved_student.name == "Section Delete Test Student"
        assert preserved_student.batch_id == batch_id
        assert preserved_student.section_id is None

    section_a = next(section for section in client.get(
        f"/api/academic/sections?department_id={cse['id']}&year_id={year_3['id']}",
        headers=headers,
    ).json() if section["name"] == "A")
    with SessionLocal() as db:
        students_before = db.query(Student).filter(Student.section_id == section_a["id"]).count()
        assert students_before > 0
        assert db.query(Section).filter(Section.id == section_a["id"]).one_or_none() is not None
        assert db.query(Student).filter(Student.section_id == section_a["id"]).count() == students_before


def test_department_seed_contains_all_nine_and_is_idempotent():
    with SessionLocal() as db:
        initial_count = db.query(Department).count()
        initial_section_count = db.query(Section).count()
        seed_database(db)
        seed_database(db)

        departments = db.query(Department).all()
        codes = [department.code for department in departments]
        names = [department.name for department in departments]

        assert EXPECTED_DEPARTMENTS.issubset(codes)
        assert len(codes) == len(set(codes))
        assert len(names) == len(set(names))
        assert db.query(Department).count() == initial_count
        assert any(department.code == "CSE" for department in departments)
        assert db.query(Section).count() == initial_section_count

        cse = db.query(Department).filter(Department.code == "CSE").one()
        year_3 = db.query(Year).filter(Year.year_number == 3).one()
        year_3_sections = db.query(Section).filter_by(
            department_id=cse.id,
            year_id=year_3.id,
        ).all()
        assert sorted(section.name for section in year_3_sections) == ["A", "B", "C"]


def test_department_api_returns_all_nine_unique_departments():
    response = client.get("/api/departments")

    assert response.status_code == 200
    departments = response.json()
    codes = [department["code"] for department in departments]
    names = [department["name"] for department in departments]

    assert EXPECTED_DEPARTMENTS.issubset(codes)
    assert len(codes) == len(set(codes))
    assert len(names) == len(set(names))
    assert "CSE" in codes


def test_cse_sections_and_subject_master_data_are_complete():
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": os.environ["OBE_SEED_ADMIN_PASSWORD"]})
    headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}
    years = client.get("/api/academic/years", headers=headers).json()
    for year in years:
        sections = client.get(
            f"/api/academic/sections?department_id=1&year_id={year['id']}",
            headers=headers,
        ).json()
        assert {section["name"] for section in sections} >= {"A", "B", "C"}

    year_3 = next(year for year in years if year["year_number"] == 3)
    semester_5 = next(
        semester
        for semester in client.get(f"/api/academic/semesters?year_id={year_3['id']}", headers=headers).json()
        if semester["semester_number"] == 5
    )
    subjects = client.get(
        _subjects_url(year_id=year_3["id"], semester_id=semester_5["id"]),
        headers=headers,
    ).json()
    subject_names = {subject["name"] for subject in subjects}
    assert {
        "DATABASE SYSTEM",
        "OPERATING SYSTEM",
        "THEORY OF COMPUTATION",
        "COMPUTER NETWORKS",
        "SOFTWARE ENGINEERING",
    }.issubset(subject_names)


# ---------------- 4. Student Management Tests ----------------
def test_student_belongs_to_section_not_subject():
    assert "semester_id" not in Student.__table__.columns
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": os.environ["OBE_SEED_ADMIN_PASSWORD"]})
    headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    # Get CSE 3rd Year Section A
    sec_resp = client.get(
        "/api/academic/sections?department_id=1&year_id=3",
        headers=headers,
    )
    sec_a = next(s for s in sec_resp.json() if s["name"] == "A")

    # Add student to Section A
    new_student_payload = {
        "register_no": "TEST-REG-9999",
        "name": "TEST STUDENT RECORD",
        "section_id": sec_a["id"],
    }
    create_resp = client.post("/api/students", json=new_student_payload, headers=headers)
    assert create_resp.status_code in (201, 400)
    if create_resp.status_code == 201:
        data = create_resp.json()
        assert data["register_no"] == "TEST-REG-9999"
        assert data["name"] == "TEST STUDENT RECORD"
        assert data["section_id"] == sec_a["id"]
        assert data["section_name"] == "A"
        assert data["department_name"] is not None
        assert "semester_id" not in data
        assert "semester_name" not in data
        # Confirm student has NO subject relation
        assert "subject_id" not in data
        assert "subject" not in data

    # Retrieve all students of Section A
    cohort_resp = client.get(f"/api/sections/{sec_a['id']}/students", headers=headers)
    assert cohort_resp.status_code == 200
    cohort = cohort_resp.json()
    assert len(cohort) >= 5
    assert any(st["register_no"] == "TEST-REG-0001" for st in cohort)

    test_student = next((st for st in cohort if st["register_no"] == "TEST-REG-9999"), None)
    if test_student:
        cleanup_resp = client.delete(f"/api/students/{test_student['id']}", headers=headers)
        assert cleanup_resp.status_code == 204


def test_student_roster_is_identical_for_semesters_five_and_six():
    cse = next(d for d in client.get("/api/departments").json() if d["code"] == "CSE")
    year_3 = next(y for y in client.get("/api/academic/years").json() if y["year_number"] == 3)
    semesters = client.get(f"/api/academic/semesters?year_id={year_3['id']}").json()
    semester_ids = {
        semester["semester_number"]: semester["id"]
        for semester in semesters
    }
    sections = client.get(
        f"/api/academic/sections?department_id={cse['id']}&year_id={year_3['id']}"
    ).json()
    section_a = next(section for section in sections if section["name"] == "A")

    rosters = [
        client.get(
            f"/api/students?department_id={cse['id']}&year_id={year_3['id']}"
            f"&section_id={section_a['id']}&semester_id={semester_ids[number]}"
        ).json()
        for number in (5, 6)
    ]
    assert [student["id"] for student in rosters[0]] == [student["id"] for student in rosters[1]]


def test_section_a_b_and_c_have_independent_student_cohorts():
    cse = next(d for d in client.get("/api/departments").json() if d["code"] == "CSE")
    year_3 = next(y for y in client.get("/api/academic/years").json() if y["year_number"] == 3)
    sections = client.get(
        f"/api/academic/sections?department_id={cse['id']}&year_id={year_3['id']}"
    ).json()
    section_ids = {section["name"]: section["id"] for section in sections}
    assert {"A", "B", "C"}.issubset(section_ids)
    assert len({section_ids[name] for name in ("A", "B", "C")}) == 3

    created_students = []
    try:
        for section_name in ("B", "C"):
            response = client.post(
                "/api/students",
                json={
                    "register_no": f"R3-ONLY-{section_name}",
                    "name": f"SECTION {section_name} TEST",
                    "section_id": section_ids[section_name],
                },
            )
            assert response.status_code == 201
            created_students.append(response.json()["id"])

        rosters = {
            name: client.get(f"/api/sections/{section_ids[name]}/students").json()
            for name in ("A", "B", "C")
        }
        registers = {
            name: {student["register_no"] for student in roster}
            for name, roster in rosters.items()
        }
        assert "TEST-REG-0001" in registers["A"]
        assert "R3-ONLY-B" in registers["B"]
        assert "R3-ONLY-C" in registers["C"]
        assert "R3-ONLY-B" not in registers["A"] | registers["C"]
        assert "R3-ONLY-C" not in registers["A"] | registers["B"]
    finally:
        for student_id in created_students:
            client.delete(f"/api/students/{student_id}")


def test_student_register_number_uniqueness():
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": os.environ["OBE_SEED_ADMIN_PASSWORD"]})
    headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    students_resp = client.get("/api/students?limit=1000", headers=headers)
    seeded_student = next(
        student for student in students_resp.json()
        if student["register_no"] == "TEST-REG-0001"
    )

    duplicate_payload = {
        "register_no": "TEST-REG-0001",  # Already seeded
        "name": "DUPLICATE ATTEMPT",
        "section_id": seeded_student["section_id"],
    }
    resp = client.post("/api/students", json=duplicate_payload, headers=headers)
    assert resp.status_code == 409
    assert "already exists in this Batch" in resp.json()["detail"]


# ---------------- 5. Subject Master Data Tests ----------------
def test_subject_is_scoped_by_department_year_semester_not_section():
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": os.environ["OBE_SEED_ADMIN_PASSWORD"]})
    headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    sub_resp = client.get(_subjects_url(), headers=headers)
    assert sub_resp.status_code == 200
    subjects = sub_resp.json()
    assert {subject["name"] for subject in subjects} == {
        "DATABASE SYSTEM",
        "COMPUTER NETWORKS",
        "OPERATING SYSTEM",
        "THEORY OF COMPUTATION",
        "SOFTWARE ENGINEERING",
    }

    for sub in subjects:
        assert "name" in sub
        assert "id" in sub
        assert sub["department_id"] == 1
        assert sub["year_id"] == 3
        assert sub["semester_id"] == 5
        assert "section_id" not in sub
        assert "code" not in sub
        assert "credits" not in sub
        assert "faculty_id" not in sub
        assert "students" not in sub


def test_semester_subject_lists_are_distinct_and_section_independent():
    semester_5 = client.get(_subjects_url(semester_id=5)).json()
    semester_6 = client.get(_subjects_url(semester_id=6)).json()
    assert {subject["name"] for subject in semester_5} == {
        "DATABASE SYSTEM",
        "COMPUTER NETWORKS",
        "OPERATING SYSTEM",
        "THEORY OF COMPUTATION",
        "SOFTWARE ENGINEERING",
    }
    assert {subject["name"] for subject in semester_6} >= {
        "WEB TECHNOLOGIES",
        "COMPILER DESIGN",
        "DISTRIBUTED COMPUTING SYSTEM",
        "ARTIFICIAL INTELLIGENCE AND MACHINE LEARNING",
    }
    section_lists = [
        client.get(_subjects_url(semester_id=5, section_id=section_id)).json()
        for section_id in (1, 2, 3)
    ]
    assert all(
        [subject["id"] for subject in subjects] == [subject["id"] for subject in section_lists[0]]
        for subjects in section_lists[1:]
    )


def test_subject_creation_and_uniqueness():
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": os.environ["OBE_SEED_ADMIN_PASSWORD"]})
    headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    payload = {
        "name": "SOFTWARE ENGINEERING",
        "department_id": 1,
        "year_id": 3,
        "semester_id": 5,
    }
    create_resp = client.post("/api/subjects", json=payload, headers=headers)
    assert create_resp.status_code == 400

    created_ids = []
    try:
        for department_id, year_id, semester_id in ((1, 3, 5), (1, 3, 6), (2, 3, 5), (1, 1, 1)):
            response = client.post(
                "/api/subjects",
                json={
                    "name": "SCOPED UNIQUENESS TEST",
                    "department_id": department_id,
                    "year_id": year_id,
                    "semester_id": semester_id,
                },
                headers=headers,
            )
            assert response.status_code == 201
            created_ids.append(response.json()["id"])

        assert len(set(created_ids)) == 4
        duplicate = client.post(
            "/api/subjects",
            json={
                "name": "SCOPED UNIQUENESS TEST",
                "department_id": 1,
                "year_id": 3,
                "semester_id": 5,
            },
            headers=headers,
        )
        assert duplicate.status_code == 400
    finally:
        for subject_id in created_ids:
            client.delete(f"/api/subjects/{subject_id}", headers=headers)


def test_used_subject_is_archived_without_changing_exam_reference():
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": os.environ["OBE_SEED_ADMIN_PASSWORD"]})
    headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}
    payload = {
        "name": "ARCHIVE PROTECTION TEST",
        "department_id": 1,
        "year_id": 3,
        "semester_id": 6,
    }
    created = client.post("/api/subjects", json=payload, headers=headers)
    assert created.status_code == 201
    subject_id = created.json()["id"]
    exam_name = "Archive Protection Subject Test"

    try:
        with SessionLocal() as db:
            section = db.query(Section).filter(
                Section.department_id == payload["department_id"],
                Section.year_id == payload["year_id"],
            ).first()
            assert section is not None
            db.add(Exam(
                name=exam_name,
                exam_type="CUSTOM",
                batch_id=section.batch_id,
                department_id=payload["department_id"],
                year_id=payload["year_id"],
                semester_id=payload["semester_id"],
                section_id=section.id,
                subject_id=subject_id,
                pass_percentage=50,
            ))
            db.commit()

        delete_response = client.delete(f"/api/subjects/{subject_id}", headers=headers)
        assert delete_response.status_code == 204
        active_subjects = client.get(_subjects_url(semester_id=6), headers=headers).json()
        all_subjects = client.get(
            f"/api/subjects?department_id=1&year_id=3&semester_id=6&include_inactive=true",
            headers=headers,
        ).json()
        assert subject_id not in {subject["id"] for subject in active_subjects}
        archived = next(subject for subject in all_subjects if subject["id"] == subject_id)
        assert archived["is_active"] is False

        with SessionLocal() as db:
            exam = db.query(Exam).filter(Exam.name == exam_name).one()
            assert exam.subject_id == subject_id
    finally:
        with SessionLocal() as db:
            exam = db.query(Exam).filter(Exam.name == exam_name).first()
            if exam:
                db.delete(exam)
            subject = db.query(Subject).filter(Subject.id == subject_id).first()
            if subject:
                db.delete(subject)
            db.commit()


def test_unused_subject_can_be_archived_and_restored_only_in_its_scope():
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": os.environ["OBE_SEED_ADMIN_PASSWORD"]})
    headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}
    payload = {
        "name": "ARCHIVE RECOVERY SCOPE TEST",
        "department_id": 1,
        "year_id": 3,
        "semester_id": 6,
    }
    created = client.post("/api/subjects", json=payload, headers=headers)
    assert created.status_code == 201
    subject_id = created.json()["id"]

    try:
        active_url = _subjects_url(semester_id=6)
        archived_url = f"{active_url}&include_inactive=true"
        assert subject_id in {item["id"] for item in client.get(active_url, headers=headers).json()}

        archived = client.delete(f"/api/subjects/{subject_id}", headers=headers)
        assert archived.status_code == 204
        assert subject_id not in {item["id"] for item in client.get(active_url, headers=headers).json()}
        archived_subject = next(
            item for item in client.get(archived_url, headers=headers).json()
            if item["id"] == subject_id
        )
        assert archived_subject["is_active"] is False

        wrong_scope = client.post(
            f"/api/subjects/{subject_id}/restore?department_id=1&year_id=3&semester_id=5",
            headers=headers,
        )
        assert wrong_scope.status_code == 404

        restored = client.post(
            f"/api/subjects/{subject_id}/restore?department_id=1&year_id=3&semester_id=6",
            headers=headers,
        )
        assert restored.status_code == 200
        assert restored.json()["is_active"] is True
        assert subject_id in {item["id"] for item in client.get(active_url, headers=headers).json()}
    finally:
        with SessionLocal() as db:
            subject = db.query(Subject).filter(Subject.id == subject_id).first()
            if subject:
                db.delete(subject)
                db.commit()
