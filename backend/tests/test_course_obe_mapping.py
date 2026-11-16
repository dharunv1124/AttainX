import importlib.util
import json
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from app.db.models import CourseCOPOMapping, Section, Subject
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)


def _subject_id() -> int:
    with SessionLocal() as db:
        subject = db.query(Subject).filter(Subject.is_active.is_(True)).order_by(Subject.id).first()
        assert subject is not None
        return subject.id


def _section_ids(subject_id: int) -> dict[str, int]:
    with SessionLocal() as db:
        subject = db.query(Subject).filter(Subject.id == subject_id).one()
        return {
            section.name: section.id
            for section in db.query(Section)
            .filter(Section.department_id == subject.department_id, Section.year_id == subject.year_id)
            .all()
        }


def test_course_co_po_mapping_load_save_update_and_subject_scope():
    subject_id = _subject_id()
    section_id = next(iter(_section_ids(subject_id).values()))
    url = f"/api/course-obe/subjects/{subject_id}/co-po-mapping?section_id={section_id}"
    empty_values = [[None for _ in range(14)] for _ in range(5)]

    initial = client.get(url)
    assert initial.status_code == 200
    assert initial.json() == {"subject_id": subject_id, "section_id": section_id, "values": empty_values}

    submitted_values = [row.copy() for row in empty_values]
    submitted_values[0][0] = 1
    submitted_values[1][1] = "-"
    submitted_values[1][2] = ""
    submitted_values[3][12] = 2
    submitted_values[4][13] = 3
    expected_values = [row.copy() for row in empty_values]
    expected_values[0][0] = 1
    expected_values[3][12] = 2
    expected_values[4][13] = 3

    saved = client.put(url, json={"values": submitted_values})
    assert saved.status_code == 200
    assert saved.json() == {"subject_id": subject_id, "section_id": section_id, "values": expected_values}
    assert client.get(url).json() == saved.json()

    updated_values = [row.copy() for row in expected_values]
    updated_values[0][0] = 3
    updated_values[3][12] = None
    updated = client.put(url, json={"values": updated_values})
    assert updated.status_code == 200
    assert updated.json() == {"subject_id": subject_id, "section_id": section_id, "values": updated_values}
    assert client.get(url).json() == updated.json()

    with SessionLocal() as db:
        count = db.execute(
            text("SELECT COUNT(*) FROM course_co_po_mappings WHERE subject_id = :subject_id AND section_id = :section_id"),
            {"subject_id": subject_id, "section_id": section_id},
        ).scalar_one()
    assert count == 1


def test_course_co_po_mapping_is_isolated_by_section():
    subject_id = _subject_id()
    section_ids = _section_ids(subject_id)
    section_a_id = section_ids["A"]
    section_b_id = section_ids["B"]
    urls = {
        section_id: f"/api/course-obe/subjects/{subject_id}/co-po-mapping?section_id={section_id}"
        for section_id in (section_a_id, section_b_id)
    }
    with SessionLocal() as db:
        originals = {
            section_id: db.query(CourseCOPOMapping).filter_by(
                subject_id=subject_id,
                section_id=section_id,
            ).first()
            for section_id in urls
        }
        original_values = {
            section_id: record.mapping_data.copy() if record else None
            for section_id, record in originals.items()
        }

    section_a_values = [[None for _ in range(14)] for _ in range(5)]
    section_a_values[0][0] = 1
    section_b_values = [[None for _ in range(14)] for _ in range(5)]
    section_b_values[0][0] = 3
    section_b_values[0][1] = 2

    try:
        assert client.put(urls[section_a_id], json={"values": section_a_values}).status_code == 200
        assert client.get(urls[section_a_id]).json()["values"] == section_a_values
        assert client.get(urls[section_b_id]).json()["values"] == (
            original_values[section_b_id] or [[None for _ in range(14)] for _ in range(5)]
        )

        assert client.put(urls[section_b_id], json={"values": section_b_values}).status_code == 200
        assert client.get(urls[section_b_id]).json()["values"] == section_b_values
        assert client.get(urls[section_a_id]).json()["values"] == section_a_values
    finally:
        with SessionLocal() as db:
            for section_id, original in original_values.items():
                record = db.query(CourseCOPOMapping).filter_by(
                    subject_id=subject_id,
                    section_id=section_id,
                ).first()
                if original is None:
                    if record is not None:
                        db.delete(record)
                elif record is not None:
                    record.mapping_data = original
            db.commit()


@pytest.mark.parametrize("invalid_value", [0, 4, 1.5, "1", True])
def test_course_co_po_mapping_rejects_invalid_values(invalid_value):
    subject_id = _subject_id()
    values = [[None for _ in range(14)] for _ in range(5)]
    values[0][0] = invalid_value

    response = client.put(
        f"/api/course-obe/subjects/{subject_id}/co-po-mapping?section_id={next(iter(_section_ids(subject_id).values()))}",
        json={"values": values},
    )

    assert response.status_code == 422


def test_course_co_po_mapping_rejects_invalid_matrix_shape():
    subject_id = _subject_id()
    response = client.put(
        f"/api/course-obe/subjects/{subject_id}/co-po-mapping?section_id={next(iter(_section_ids(subject_id).values()))}",
        json={"values": [[None for _ in range(14)] for _ in range(4)]},
    )

    assert response.status_code == 422


def test_course_co_po_mapping_migration_creates_isolated_subject_table(tmp_path):
    database = create_engine(f"sqlite:///{tmp_path / 'course_obe_mapping.sqlite'}")
    with database.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE subjects (id INTEGER PRIMARY KEY)")

    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "011_course_co_po_mapping.py"
    )
    spec = importlib.util.spec_from_file_location("course_co_po_mapping", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with database.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    inspector = inspect(database)
    assert "course_co_po_mappings" in inspector.get_table_names()
    assert inspector.get_foreign_keys("course_co_po_mappings")[0]["referred_table"] == "subjects"
    assert inspector.get_unique_constraints("course_co_po_mappings") == [
        {"name": "uq_course_co_po_mapping_subject", "column_names": ["subject_id"]}
    ]
    database.dispose()


def test_course_obe_section_migration_preserves_legacy_rows_and_allows_section_rows(tmp_path):
    database = create_engine(f"sqlite:///{tmp_path / 'course_obe_section_scope.sqlite'}")
    legacy_mapping = [[1] + [None] * 13 for _ in range(5)]
    legacy_inputs = [{"a": 91, "b": None, "c": None, "university": None, "g": None} for _ in range(5)]
    with database.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE subjects (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE sections (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO subjects (id) VALUES (7)")
        connection.exec_driver_sql("INSERT INTO sections (id) VALUES (10), (11)")
        connection.exec_driver_sql(
            "CREATE TABLE course_co_po_mappings (id INTEGER PRIMARY KEY, subject_id INTEGER NOT NULL, "
            "mapping_data JSON NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
            "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
            "CONSTRAINT uq_course_co_po_mapping_subject UNIQUE (subject_id), "
            "FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE course_co_attainment_inputs (id INTEGER PRIMARY KEY, subject_id INTEGER NOT NULL, "
            "input_data JSON NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
            "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
            "CONSTRAINT uq_course_co_attainment_subject UNIQUE (subject_id), "
            "FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE)"
        )
        connection.execute(
            text("INSERT INTO course_co_po_mappings (id, subject_id, mapping_data) VALUES (1, 7, :data)"),
            {"data": json.dumps(legacy_mapping)},
        )
        connection.execute(
            text("INSERT INTO course_co_attainment_inputs (id, subject_id, input_data) VALUES (1, 7, :data)"),
            {"data": json.dumps(legacy_inputs)},
        )

    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "015_course_obe_section_scope.py"
    )
    spec = importlib.util.spec_from_file_location("course_obe_section_scope", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with database.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    with database.begin() as connection:
        assert connection.execute(
            text("SELECT section_id, mapping_data FROM course_co_po_mappings WHERE id = 1")
        ).one() == (None, json.dumps(legacy_mapping))
        assert connection.execute(
            text("SELECT section_id, input_data FROM course_co_attainment_inputs WHERE id = 1")
        ).one() == (None, json.dumps(legacy_inputs))
        connection.execute(
            text("INSERT INTO course_co_po_mappings (subject_id, section_id, mapping_data) VALUES (7, 10, :data)"),
            {"data": "[]"},
        )
        connection.execute(
            text("INSERT INTO course_co_po_mappings (subject_id, section_id, mapping_data) VALUES (7, 11, :data)"),
            {"data": "[]"},
        )
        connection.execute(
            text("INSERT INTO course_co_attainment_inputs (subject_id, section_id, input_data) VALUES (7, 10, :data)"),
            {"data": "[]"},
        )
        connection.execute(
            text("INSERT INTO course_co_attainment_inputs (subject_id, section_id, input_data) VALUES (7, 11, :data)"),
            {"data": "[]"},
        )

    database.dispose()