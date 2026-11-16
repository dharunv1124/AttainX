import os
from datetime import date, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.models import Exam, ExamQuestion, Student, StudentMark
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)


def _headers():
    response = client.post(
        "/api/auth/login",
        json={"username": "faculty1", "password": os.environ["OBE_SEED_FACULTY_PASSWORD"]},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _context(headers):
    departments = client.get("/api/departments", headers=headers).json()
    department = next(item for item in departments if item["code"] == "CSE")
    years = client.get("/api/academic/years", headers=headers).json()
    year = next(item for item in years if item["year_number"] == 3)
    semesters = client.get(f"/api/academic/semesters?year_id={year['id']}", headers=headers).json()
    semester = next(item for item in semesters if item["semester_number"] == 6)
    sections = client.get(
        f"/api/academic/sections?department_id={department['id']}&year_id={year['id']}",
        headers=headers,
    ).json()
    section = next(item for item in sections if item["name"] == "A")
    subjects = client.get(
        f"/api/subjects?department_id={department['id']}&year_id={year['id']}&semester_id={semester['id']}",
        headers=headers,
    ).json()
    subject = next(item for item in subjects if item["name"] == "WEB TECHNOLOGIES")
    return {
        "department_id": department["id"],
        "year_id": year["id"],
        "semester_id": semester["id"],
        "section_id": section["id"],
        "subject_id": subject["id"],
    }


def _create_exam(headers, context, name):
    response = client.post(
        "/api/exams",
        headers=headers,
        json={
            "name": name,
            "exam_type": "CUSTOM",
            "exam_date": (date.today() + timedelta(days=1)).isoformat(),
            **context,
            "pass_percentage": 50,
            "covered_cos": ["CO1"],
            "questions": [{"question_number": "Q1", "max_marks": 10, "co_code": "CO1"}],
        },
    )
    assert response.status_code == 201
    return response.json()


def _save_mark(headers, exam_id):
    response = client.post(
        f"/api/exams/{exam_id}/marks",
        headers=headers,
        json={"marks": [{"register_no": "TEST-REG-0001", "question_number": "Q1", "obtained_mark": 7}]},
    )
    assert response.status_code == 200


def test_delete_exam_removes_only_its_configuration_and_marks():
    headers = _headers()
    context = _context(headers)
    target_exam = _create_exam(headers, context, f"Delete target {uuid4()}")
    other_exam = _create_exam(headers, context, f"Preserved exam {uuid4()}")
    _save_mark(headers, target_exam["id"])
    _save_mark(headers, other_exam["id"])

    mapping = [[None for _ in range(14)] for _ in range(5)]
    mapping[0][0] = 2
    mapping_url = f"/api/course-obe/subjects/{context['subject_id']}/co-po-mapping?section_id={context['section_id']}"
    saved_mapping = client.put(mapping_url, headers=headers, json={"values": mapping})
    assert saved_mapping.status_code == 200

    inputs = [
        {"a": None, "b": None, "c": None, "university": None, "g": None}
        for _ in range(5)
    ]
    inputs[0]["a"] = 75
    attainment_url = f"/api/course-obe/subjects/{context['subject_id']}/overall-co-attainment?section_id={context['section_id']}"
    saved_attainment = client.put(attainment_url, headers=headers, json={"inputs": inputs})
    assert saved_attainment.status_code == 200

    with SessionLocal() as db:
        student_count_before = db.query(Student).filter(Student.section_id == context["section_id"]).count()

    deletion = client.delete(f"/api/exams/{target_exam['id']}", headers=headers)
    assert deletion.status_code == 204
    assert client.get(f"/api/exams/{target_exam['id']}", headers=headers).status_code == 404
    assert client.get(f"/api/exams/{target_exam['id']}/questions", headers=headers).status_code == 404
    assert client.get(f"/api/exams/{target_exam['id']}/marks", headers=headers).status_code == 404

    other_exam_after = client.get(f"/api/exams/{other_exam['id']}", headers=headers)
    assert other_exam_after.status_code == 200
    assert other_exam_after.json()["questions"] == other_exam["questions"]
    other_marks_after = client.get(f"/api/exams/{other_exam['id']}/marks", headers=headers)
    assert other_marks_after.status_code == 200
    assert len(other_marks_after.json()["marks"]) == 1

    assert client.get(mapping_url, headers=headers).json() == saved_mapping.json()
    assert client.get(attainment_url, headers=headers).json()["inputs"] == inputs
    with SessionLocal() as db:
        student_count_after = db.query(Student).filter(Student.section_id == context["section_id"]).count()
    assert student_count_after == student_count_before


def test_failed_exam_delete_rolls_back_all_changes():
    headers = _headers()
    target_exam = _create_exam(headers, _context(headers), f"Rollback target {uuid4()}")
    _save_mark(headers, target_exam["id"])

    with SessionLocal() as db:
        db.execute(text(
            "CREATE TRIGGER reject_exam_question_delete "
            "BEFORE DELETE ON exam_questions "
            f"WHEN OLD.exam_id = {target_exam['id']} "
            "BEGIN SELECT RAISE(ABORT, 'forced delete failure'); END"
        ))
        db.commit()

    try:
        failing_client = TestClient(app, raise_server_exceptions=False)
        response = failing_client.delete(f"/api/exams/{target_exam['id']}", headers=headers)
        assert response.status_code == 500
    finally:
        with SessionLocal() as db:
            db.execute(text("DROP TRIGGER IF EXISTS reject_exam_question_delete"))
            db.commit()

    with SessionLocal() as db:
        assert db.query(Exam).filter(Exam.id == target_exam["id"]).count() == 1
        assert db.query(ExamQuestion).filter(ExamQuestion.exam_id == target_exam["id"]).count() == 1
        assert db.query(StudentMark).filter(StudentMark.exam_id == target_exam["id"]).count() == 1
