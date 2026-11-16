import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.models import (
    CourseCOAttainmentInputs,
    CourseCOPOMapping,
    Exam,
    ExamCoveredCO,
    ExamQuestion,
    Section,
    Student,
    StudentMark,
    Subject,
)
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)


def _headers():
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": os.environ["OBE_SEED_ADMIN_PASSWORD"]},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_subject(headers, name):
    response = client.post(
        "/api/subjects",
        headers=headers,
        json={
            "name": name,
            "department_id": 1,
            "year_id": 3,
            "semester_id": 6,
        },
    )
    assert response.status_code == 201
    return response.json()


def _subject_list_url(include_inactive=False):
    return "/api/subjects?department_id=1&year_id=3&semester_id=6" + (
        "&include_inactive=true" if include_inactive else ""
    )


def _section_context(headers):
    sections = client.get(
        "/api/academic/sections?department_id=1&year_id=3",
        headers=headers,
    ).json()
    return next(item for item in sections if item["name"] == "A")


def _create_exam(headers, subject_id, section_id, name, questions):
    response = client.post(
        "/api/exams",
        headers=headers,
        json={
            "name": name,
            "exam_type": "CUSTOM",
            "exam_date": "2026-10-04",
            "department_id": 1,
            "year_id": 3,
            "semester_id": 6,
            "section_id": section_id,
            "subject_id": subject_id,
            "pass_percentage": 50,
            "covered_cos": ["CO1"],
            "questions": questions,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _course_data(headers, subject_id, cell_value):
    section_id = _section_context(headers)["id"]
    mapping = [[None for _ in range(14)] for _ in range(5)]
    mapping[0][0] = cell_value
    mapping_url = f"/api/course-obe/subjects/{subject_id}/co-po-mapping?section_id={section_id}"
    mapping_response = client.put(mapping_url, headers=headers, json={"values": mapping})
    assert mapping_response.status_code == 200, mapping_response.text

    inputs = [
        {"a": None, "b": None, "c": None, "university": None, "g": None}
        for _ in range(5)
    ]
    inputs[0]["a"] = 70 + cell_value
    attainment_url = f"/api/course-obe/subjects/{subject_id}/overall-co-attainment?section_id={section_id}"
    attainment_response = client.put(attainment_url, headers=headers, json={"inputs": inputs})
    assert attainment_response.status_code == 200, attainment_response.text
    return mapping_url, mapping_response.json(), attainment_url, inputs


def test_permanent_delete_removes_only_an_archived_subject_without_dependencies():
    headers = _headers()
    subject = _create_subject(headers, f"No history {uuid4()}")
    subject_id = subject["id"]

    active_delete = client.delete(f"/api/subjects/{subject_id}/permanent", headers=headers)
    assert active_delete.status_code == 409
    assert subject_id in {item["id"] for item in client.get(_subject_list_url(), headers=headers).json()}

    archive = client.delete(f"/api/subjects/{subject_id}", headers=headers)
    assert archive.status_code == 204
    assert subject_id not in {item["id"] for item in client.get(_subject_list_url(), headers=headers).json()}
    assert subject_id in {
        item["id"] for item in client.get(_subject_list_url(include_inactive=True), headers=headers).json()
    }

    permanent_delete = client.delete(f"/api/subjects/{subject_id}/permanent", headers=headers)
    assert permanent_delete.status_code == 204
    assert subject_id not in {item["id"] for item in client.get(_subject_list_url(include_inactive=True), headers=headers).json()}


def test_permanent_delete_cascades_only_selected_archived_subject_data():
    headers = _headers()
    subject = _create_subject(headers, f"Cascade target {uuid4()}")
    other_subject = _create_subject(headers, f"Cascade sibling {uuid4()}")
    subject_id = subject["id"]
    section = _section_context(headers)
    target_exam = _create_exam(
        headers,
        subject_id,
        section["id"],
        f"Target exam {uuid4()}",
        [
            {"question_number": "Q1", "max_marks": 10, "co_code": "CO1"},
            {"question_number": "Q2", "max_marks": 10, "co_code": "CO1"},
        ],
    )
    other_exam = _create_exam(
        headers,
        other_subject["id"],
        section["id"],
        f"Sibling exam {uuid4()}",
        [{"question_number": "Q1", "max_marks": 10, "co_code": "CO1"}],
    )
    students = client.get(
        f"/api/sections/{section['id']}/students",
        headers=headers,
    ).json()
    assert students

    with SessionLocal() as db:
        db.add_all([
            StudentMark(exam_id=target_exam["id"], student_id=students[0]["id"], question_number="Q1", obtained_mark=8),
            StudentMark(exam_id=target_exam["id"], student_id=students[0]["id"], question_number="Q2", obtained_mark=7),
            StudentMark(exam_id=other_exam["id"], student_id=students[0]["id"], question_number="Q1", obtained_mark=6),
        ])
        db.commit()

    mapping_url, saved_mapping, attainment_url, inputs = _course_data(headers, subject_id, 2)
    other_mapping_url, other_mapping, other_attainment_url, other_inputs = _course_data(
        headers, other_subject["id"], 3
    )

    with SessionLocal() as db:
        student_count_before = db.query(Student).filter(Student.section_id == section["id"]).count()

    archived = client.delete(f"/api/subjects/{subject_id}", headers=headers)
    assert archived.status_code == 204

    delete_response = client.delete(f"/api/subjects/{subject_id}/permanent", headers=headers)
    assert delete_response.status_code == 204, delete_response.text
    assert client.get(f"/api/subjects/{subject_id}", headers=headers).status_code == 404
    assert subject_id not in {
        item["id"] for item in client.get(_subject_list_url(include_inactive=True), headers=headers).json()
    }
    assert client.get(f"/api/exams/{target_exam['id']}", headers=headers).status_code == 404
    assert client.get(f"/api/exams/{target_exam['id']}/questions", headers=headers).status_code == 404
    assert client.get(f"/api/exams/{target_exam['id']}/marks", headers=headers).status_code == 404
    assert client.get(f"/api/exams/{other_exam['id']}", headers=headers).status_code == 200
    assert len(client.get(f"/api/exams/{other_exam['id']}/marks", headers=headers).json()["marks"]) == 1
    assert client.get(f"/api/subjects/{other_subject['id']}", headers=headers).status_code == 200
    assert client.get(other_mapping_url, headers=headers).json() == other_mapping
    assert client.get(other_attainment_url, headers=headers).json()["inputs"] == other_inputs

    with SessionLocal() as db:
        assert db.query(Exam).filter(Exam.subject_id == subject_id).count() == 0
        assert db.query(ExamQuestion).filter(ExamQuestion.exam_id == target_exam["id"]).count() == 0
        assert db.query(ExamCoveredCO).filter(ExamCoveredCO.exam_id == target_exam["id"]).count() == 0
        assert db.query(StudentMark).filter(StudentMark.exam_id == target_exam["id"]).count() == 0
        assert db.query(CourseCOPOMapping).filter(CourseCOPOMapping.subject_id == subject_id).count() == 0
        assert db.query(CourseCOAttainmentInputs).filter(
            CourseCOAttainmentInputs.subject_id == subject_id
        ).count() == 0
        assert db.query(Exam).filter(Exam.id == other_exam["id"], Exam.subject_id == other_subject["id"]).count() == 1
        assert db.query(StudentMark).filter(StudentMark.exam_id == other_exam["id"]).count() == 1
        assert db.query(CourseCOPOMapping).filter(CourseCOPOMapping.subject_id == other_subject["id"]).count() == 1
        assert db.query(CourseCOAttainmentInputs).filter(
            CourseCOAttainmentInputs.subject_id == other_subject["id"]
        ).count() == 1
        assert db.query(Student).filter(Student.id == students[0]["id"]).count() == 1
        assert db.query(Section).filter(Section.id == section["id"]).count() == 1
        assert db.query(Subject).filter(Subject.id == other_subject["id"]).count() == 1
        assert db.query(Student).filter(Student.section_id == section["id"]).count() == student_count_before

    assert saved_mapping["values"] != other_mapping["values"]
    assert inputs != other_inputs


def test_failed_permanent_delete_rolls_back_all_subject_data():
    headers = _headers()
    subject = _create_subject(headers, f"Delete rollback {uuid4()}")
    subject_id = subject["id"]
    section = _section_context(headers)
    exam = _create_exam(
        headers,
        subject_id,
        section["id"],
        f"Rollback exam {uuid4()}",
        [{"question_number": "Q1", "max_marks": 10, "co_code": "CO1"}],
    )
    students = client.get(f"/api/sections/{section['id']}/students", headers=headers).json()
    with SessionLocal() as db:
        db.add(StudentMark(
            exam_id=exam["id"],
            student_id=students[0]["id"],
            question_number="Q1",
            obtained_mark=5,
        ))
        db.commit()
    mapping_url, _, attainment_url, _ = _course_data(headers, subject_id, 2)
    archived = client.delete(f"/api/subjects/{subject_id}", headers=headers)
    assert archived.status_code == 204

    with SessionLocal() as db:
        db.execute(text(
            "CREATE TRIGGER reject_subject_delete "
            "BEFORE DELETE ON subjects "
            f"WHEN OLD.id = {subject_id} "
            "BEGIN SELECT RAISE(ABORT, 'forced delete failure'); END"
        ))
        db.commit()

    try:
        failing_client = TestClient(app, raise_server_exceptions=False)
        response = failing_client.delete(f"/api/subjects/{subject_id}/permanent", headers=headers)
        assert response.status_code == 500
    finally:
        with SessionLocal() as db:
            db.execute(text("DROP TRIGGER IF EXISTS reject_subject_delete"))
            db.commit()

    archived_subjects = client.get(_subject_list_url(include_inactive=True), headers=headers).json()
    assert any(item["id"] == subject_id and item["is_active"] is False for item in archived_subjects)
    with SessionLocal() as db:
        assert db.query(Subject).filter(Subject.id == subject_id).count() == 1
        assert db.query(Exam).filter(Exam.id == exam["id"]).count() == 1
        assert db.query(ExamQuestion).filter(ExamQuestion.exam_id == exam["id"]).count() == 1
        assert db.query(ExamCoveredCO).filter(ExamCoveredCO.exam_id == exam["id"]).count() == 1
        assert db.query(StudentMark).filter(StudentMark.exam_id == exam["id"]).count() == 1
        assert db.query(CourseCOPOMapping).filter(CourseCOPOMapping.subject_id == subject_id).count() == 1
        assert db.query(CourseCOAttainmentInputs).filter(
            CourseCOAttainmentInputs.subject_id == subject_id
        ).count() == 1
    assert client.get(mapping_url, headers=headers).status_code == 200
    assert client.get(attainment_url, headers=headers).status_code == 200
