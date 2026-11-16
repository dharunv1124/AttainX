import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text

from app.domain.attainment_levels import classify_attainment_level
from app.domain.course_obe_attainment import (
    calculate_course_overall_co_attainment,
    calculate_course_po_attainment_overall,
)
from app.db.models import CourseCOAttainmentInputs, Section, Subject
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)


@pytest.mark.parametrize(
    ("percentage", "expected"),
    [
        (54.99, None),
        (55, 1),
        (59.99, 1),
        (60, 2),
        (64.99, 2),
        (65, None),
        (65.01, 3),
    ],
)
def test_shared_attainment_level_boundaries(percentage, expected):
    assert classify_attainment_level(percentage) == expected


def _subject_id() -> int:
    with SessionLocal() as db:
        subject = db.query(Subject).filter(Subject.is_active.is_(True)).order_by(Subject.id).first()
        assert subject is not None
        return subject.id


def _other_subject_id(subject_id: int) -> int:
    with SessionLocal() as db:
        subject = (
            db.query(Subject)
            .filter(Subject.is_active.is_(True), Subject.id != subject_id)
            .order_by(Subject.id)
            .first()
        )
        assert subject is not None
        return subject.id


def _section_id(subject_id: int, section_name: str = "A") -> int:
    with SessionLocal() as db:
        subject = db.query(Subject).filter(Subject.id == subject_id).one()
        section = db.query(Section).filter_by(
            department_id=subject.department_id,
            year_id=subject.year_id,
            name=section_name,
        ).one()
        return section.id


def _empty_inputs():
    return [
        {"a": None, "b": None, "c": None, "university": None, "g": None}
        for _ in range(5)
    ]


@pytest.mark.parametrize(
    ("assessment_values", "expected_average", "expected_attainment"),
    [
        ((93.30, 94.0, 95.21), 94.17, 3),
        ((93.30, None, 95.21), 94.255, 3),
        ((None, 89.40, 93.23), 91.315, 3),
        ((None, None, 87.46), 87.46, 3),
        ((None, None, 89.19), 89.19, 3),
        ((None, 60, None), 60, 2),
        ((None, None, None), None, None),
    ],
)
def test_course_overall_co_attainment_averages_only_entered_assessments(
    assessment_values,
    expected_average,
    expected_attainment,
):
    result = calculate_course_overall_co_attainment([{
        "a": assessment_values[0],
        "b": assessment_values[1],
        "c": assessment_values[2],
        "university": 90,
        "g": 3,
    }])[0]

    if expected_average is None:
        assert result["average"] is None
        assert result["attainment"] is None
        assert result["d"] is None
        assert result["f"] is None
        assert result["ninety_percent_f"] is None
        assert result["overall_co"] is None
        assert result["university_attainment"] == 3
        assert result["e"] == pytest.approx(2.4)
        assert result["ten_percent_g"] == pytest.approx(0.3)
    else:
        assert result["average"] == pytest.approx(expected_average)
        assert result["attainment"] == expected_attainment
        assert result["d"] == pytest.approx(expected_attainment * 0.2)


@pytest.fixture
def course_obe_test_subject():
    subject_id = _subject_id()
    section_id = _section_id(subject_id)
    mapping_url = f"/api/course-obe/subjects/{subject_id}/co-po-mapping?section_id={section_id}"
    overall_url = f"/api/course-obe/subjects/{subject_id}/overall-co-attainment?section_id={section_id}"
    initial_mapping = client.get(mapping_url).json()["values"]
    initial_inputs = client.get(overall_url).json()["inputs"]
    yield subject_id, section_id
    client.put(mapping_url, json={"values": initial_mapping})
    client.put(overall_url, json={"inputs": initial_inputs})


def test_course_overall_co_attainment_calculates_persists_and_updates():
    subject_id = _subject_id()
    section_id = _section_id(subject_id)
    url = f"/api/course-obe/subjects/{subject_id}/overall-co-attainment?section_id={section_id}"
    empty_response = client.get(url)
    assert empty_response.status_code == 200
    assert empty_response.json()["inputs"] == _empty_inputs()

    inputs = _empty_inputs()
    inputs[0] = {"a": 93.30, "b": 0, "c": 95.21, "university": 90, "g": 3}
    inputs[2] = {"a": 95, "b": 95, "c": 95, "university": None, "g": 3}
    inputs[3] = {"a": 65, "b": 65, "c": 65, "university": 65, "g": None}

    saved = client.put(url, json={"inputs": inputs})
    assert saved.status_code == 200
    body = saved.json()
    assert body["inputs"] == inputs

    sample = body["results"][0]
    assert sample["average"] == pytest.approx(62.8366666667)
    assert sample["attainment"] == 2
    assert sample["university_attainment"] == 3
    assert sample["d"] == pytest.approx(0.4)
    assert sample["e"] == pytest.approx(2.4)
    assert sample["f"] == pytest.approx(2.8)
    assert sample["ninety_percent_f"] == pytest.approx(2.52)
    assert sample["ten_percent_g"] == pytest.approx(0.3)
    assert sample["overall_co"] == pytest.approx(2.82)

    incomplete = body["results"][1]
    assert all(value is None for value in incomplete.values())
    partial = body["results"][2]
    assert partial["average"] == pytest.approx(95)
    assert partial["attainment"] == 3
    assert partial["d"] == pytest.approx(0.6)
    assert partial["e"] is None
    assert partial["f"] is None
    assert partial["ninety_percent_f"] is None
    assert partial["ten_percent_g"] == pytest.approx(0.3)
    assert partial["overall_co"] is None

    unresolved_boundary = body["results"][3]
    assert unresolved_boundary["average"] == pytest.approx(65)
    assert unresolved_boundary["attainment"] is None
    assert unresolved_boundary["university_attainment"] is None
    assert unresolved_boundary["d"] is None
    assert unresolved_boundary["e"] is None

    assert client.get(url).json() == body

    inputs[0]["a"] = 100
    updated = client.put(url, json={"inputs": inputs})
    assert updated.status_code == 200
    assert updated.json()["results"][0]["average"] == pytest.approx(65.07)
    assert updated.json()["results"][0]["attainment"] == 3
    assert client.get(url).json() == updated.json()

    with SessionLocal() as db:
        count = db.execute(
            text("SELECT COUNT(*) FROM course_co_attainment_inputs WHERE subject_id = :subject_id AND section_id = :section_id"),
            {"subject_id": subject_id, "section_id": section_id},
        ).scalar_one()
    assert count == 1


def test_course_overall_co_attainment_is_isolated_by_section():
    subject_id = _subject_id()
    section_a_id = _section_id(subject_id, "A")
    section_b_id = _section_id(subject_id, "B")
    urls = {
        section_id: f"/api/course-obe/subjects/{subject_id}/overall-co-attainment?section_id={section_id}"
        for section_id in (section_a_id, section_b_id)
    }
    with SessionLocal() as db:
        originals = {
            section_id: db.query(CourseCOAttainmentInputs).filter_by(
                subject_id=subject_id,
                section_id=section_id,
            ).first()
            for section_id in urls
        }
        original_inputs = {
            section_id: deepcopy(record.input_data) if record else None
            for section_id, record in originals.items()
        }

    inputs_a = _empty_inputs()
    inputs_a[0]["a"] = 91
    inputs_b = _empty_inputs()
    inputs_b[0]["a"] = 62
    inputs_b[0]["g"] = 2

    try:
        assert client.put(urls[section_a_id], json={"inputs": inputs_a}).status_code == 200
        assert client.get(urls[section_a_id]).json()["inputs"] == inputs_a
        assert client.get(urls[section_b_id]).json()["inputs"] == (
            original_inputs[section_b_id] or _empty_inputs()
        )

        assert client.put(urls[section_b_id], json={"inputs": inputs_b}).status_code == 200
        assert client.get(urls[section_b_id]).json()["inputs"] == inputs_b
        assert client.get(urls[section_a_id]).json()["inputs"] == inputs_a
    finally:
        with SessionLocal() as db:
            for section_id, original in original_inputs.items():
                record = db.query(CourseCOAttainmentInputs).filter_by(
                    subject_id=subject_id,
                    section_id=section_id,
                ).first()
                if original is None:
                    if record is not None:
                        db.delete(record)
                elif record is not None:
                    record.input_data = original
            db.commit()


def test_course_po_attainment_derives_from_mapping_and_overall_co_updates(course_obe_test_subject):
    subject_id, section_id = course_obe_test_subject
    mapping_url = f"/api/course-obe/subjects/{subject_id}/co-po-mapping?section_id={section_id}"
    overall_url = f"/api/course-obe/subjects/{subject_id}/overall-co-attainment?section_id={section_id}"
    po_url = f"/api/course-obe/subjects/{subject_id}/po-attainment?section_id={section_id}"
    mappings = [[None for _ in range(14)] for _ in range(5)]
    mappings[0][0] = 3
    mappings[0][1] = 2
    mappings[1][0] = 3
    assert client.put(mapping_url, json={"values": mappings}).status_code == 200

    inputs = _empty_inputs()
    inputs[0] = {"a": 93.30, "b": 0, "c": 95.21, "university": 90, "g": 3}
    inputs[1] = {"a": 90, "b": 90, "c": 90, "university": 90, "g": None}
    assert client.put(overall_url, json={"inputs": inputs}).status_code == 200

    result = client.get(po_url)
    assert result.status_code == 200
    values = result.json()["values"]
    overall_values = result.json()["overall_values"]
    assert values[0][0] == pytest.approx(2.82)
    assert values[0][1] == pytest.approx(1.88)
    assert values[0][2] is None
    assert values[1][0] is None
    assert overall_values[0] == pytest.approx(2.82)
    assert overall_values[1] == pytest.approx(1.88)
    assert all(value is None for value in overall_values[2:])

    mappings[0][0] = 2
    assert client.put(mapping_url, json={"values": mappings}).status_code == 200
    updated_mapping = client.get(po_url).json()["values"]
    assert updated_mapping[0][0] == pytest.approx(1.88)

    inputs[0]["g"] = 2
    assert client.put(overall_url, json={"inputs": inputs}).status_code == 200
    updated_overall = client.get(po_url).json()["values"]
    assert updated_overall[0][0] == pytest.approx(1.8133333333)
    assert client.get(po_url).json()["values"] == updated_overall


def test_course_po_attainment_overall_averages_only_available_numeric_values():
    values = [
        [1.0, None, None],
        [3.0, 2.0, None],
        [None, 4.0, None],
        [None, None, None],
        [None, None, None],
    ]

    assert calculate_course_po_attainment_overall(values) == [2.0, 3.0, None]


def test_course_obe_clear_and_resave_are_subject_scoped(course_obe_test_subject):
    subject_id, section_id = course_obe_test_subject
    other_subject_id = _other_subject_id(subject_id)
    other_section_id = _section_id(other_subject_id)
    base_url = f"/api/course-obe/subjects/{subject_id}"
    other_base_url = f"/api/course-obe/subjects/{other_subject_id}"
    mapping_url = f"{base_url}/co-po-mapping?section_id={section_id}"
    overall_url = f"{base_url}/overall-co-attainment?section_id={section_id}"
    po_url = f"{base_url}/po-attainment?section_id={section_id}"
    other_mapping_url = f"{other_base_url}/co-po-mapping?section_id={other_section_id}"
    other_overall_url = f"{other_base_url}/overall-co-attainment?section_id={other_section_id}"
    other_mapping_before = client.get(other_mapping_url).json()
    other_overall_before = client.get(other_overall_url).json()

    mappings = [[None for _ in range(14)] for _ in range(5)]
    mappings[0][0] = 3
    inputs = _empty_inputs()
    inputs[0] = {"a": 93, "b": None, "c": 95, "university": 90, "g": 3}
    assert client.put(mapping_url, json={"values": mappings}).status_code == 200
    assert client.put(overall_url, json={"inputs": inputs}).status_code == 200
    assert client.get(po_url).json()["values"][0][0] == pytest.approx(3.0)

    cleared_mappings = [[None for _ in range(14)] for _ in range(5)]
    cleared_mapping_response = client.put(mapping_url, json={"values": cleared_mappings})
    assert cleared_mapping_response.status_code == 200
    assert cleared_mapping_response.json()["values"] == cleared_mappings
    assert client.get(overall_url).json()["inputs"] == inputs
    po_after_mapping_clear = client.get(po_url).json()
    assert all(value is None for row in po_after_mapping_clear["values"] for value in row)
    assert all(value is None for value in po_after_mapping_clear["overall_values"])

    cleared_overall_response = client.put(overall_url, json={"inputs": _empty_inputs()})
    assert cleared_overall_response.status_code == 200
    cleared_overall = cleared_overall_response.json()
    assert cleared_overall["inputs"] == _empty_inputs()
    assert all(
        value is None
        for result in cleared_overall["results"]
        for value in result.values()
    )
    assert client.get(mapping_url).json()["values"] == cleared_mappings

    assert client.get(other_mapping_url).json() == other_mapping_before
    assert client.get(other_overall_url).json() == other_overall_before

    assert client.put(mapping_url, json={"values": mappings}).status_code == 200
    assert client.put(overall_url, json={"inputs": inputs}).status_code == 200
    assert client.get(po_url).json()["values"][0][0] == pytest.approx(3.0)


@pytest.mark.parametrize("invalid_value", [True, "90"])
def test_course_overall_co_attainment_rejects_non_finite_or_non_numeric_inputs(invalid_value):
    subject_id = _subject_id()
    section_id = _section_id(subject_id)
    inputs = _empty_inputs()
    inputs[0]["a"] = invalid_value

    response = client.put(
        f"/api/course-obe/subjects/{subject_id}/overall-co-attainment?section_id={section_id}",
        json={"inputs": inputs},
    )

    assert response.status_code == 422


@pytest.mark.parametrize("invalid_value", [float("nan"), float("inf")])
def test_course_overall_co_attainment_schema_rejects_non_finite_numbers(invalid_value):
    from app.schemas.course_obe_attainment import CourseCOAttainmentInputRow

    with pytest.raises(ValidationError):
        CourseCOAttainmentInputRow(
            a=invalid_value,
            b=None,
            c=None,
            university=None,
            g=None,
        )


def test_course_overall_co_attainment_migration_creates_separate_subject_table(tmp_path):
    database = create_engine(f"sqlite:///{tmp_path / 'course_co_attainment.sqlite'}")
    with database.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE subjects (id INTEGER PRIMARY KEY)")

    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "012_course_co_attainment_inputs.py"
    )
    spec = importlib.util.spec_from_file_location("course_co_attainment_inputs", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with database.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    inspector = inspect(database)
    assert "course_co_attainment_inputs" in inspector.get_table_names()
    assert inspector.get_foreign_keys("course_co_attainment_inputs")[0]["referred_table"] == "subjects"
    assert inspector.get_unique_constraints("course_co_attainment_inputs") == [
        {"name": "uq_course_co_attainment_subject", "column_names": ["subject_id"]}
    ]
    database.dispose()