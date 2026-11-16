import os
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _headers():
    response = client.post(
        "/api/auth/login",
        json={"username": "faculty1", "password": os.environ["OBE_SEED_FACULTY_PASSWORD"]},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _exam_context(headers):
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


def test_saved_custom_pattern_crud_and_exam_isolation():
    headers = _headers()
    pattern_name = f"Reusable pattern {uuid4()}"
    pattern_payload = {
        "name": pattern_name,
        "groups": [
            {"quantity": 5, "marks_per_question": 2},
            {"quantity": 2, "marks_per_question": 13},
            {"quantity": 1, "marks_per_question": 14},
        ],
    }

    create_pattern = client.post("/api/custom-exam-patterns", json=pattern_payload, headers=headers)
    assert create_pattern.status_code == 201
    saved_pattern = create_pattern.json()
    assert saved_pattern["name"] == pattern_name
    assert saved_pattern["groups"] == pattern_payload["groups"]

    listed_patterns = client.get("/api/custom-exam-patterns", headers=headers)
    assert listed_patterns.status_code == 200
    assert any(pattern["id"] == saved_pattern["id"] for pattern in listed_patterns.json())

    duplicate_pattern = client.post("/api/custom-exam-patterns", json=pattern_payload, headers=headers)
    assert duplicate_pattern.status_code == 409

    invalid_pattern = client.post(
        "/api/custom-exam-patterns",
        json={"name": f"Invalid {uuid4()}", "groups": [{"quantity": 0, "marks_per_question": -1}]},
        headers=headers,
    )
    assert invalid_pattern.status_code == 422

    context = _exam_context(headers)
    exam_response = client.post(
        "/api/exams",
        json={
            "name": f"Preset isolation exam {uuid4()}",
            "exam_type": "CUSTOM",
            "exam_date": "2026-10-04",
            **context,
            "pass_percentage": 50,
            "covered_cos": ["CO1"],
            "questions": [{"question_number": "Q1", "max_marks": 10, "co_code": "CO1"}],
        },
        headers=headers,
    )
    assert exam_response.status_code == 201
    exam_id = exam_response.json()["id"]

    delete_pattern = client.delete(f"/api/custom-exam-patterns/{saved_pattern['id']}", headers=headers)
    assert delete_pattern.status_code == 204
    remaining_patterns = client.get("/api/custom-exam-patterns", headers=headers).json()
    assert all(pattern["id"] != saved_pattern["id"] for pattern in remaining_patterns)

    unchanged_exam = client.get(f"/api/exams/{exam_id}", headers=headers)
    assert unchanged_exam.status_code == 200
    assert unchanged_exam.json()["questions"] == exam_response.json()["questions"]
    assert unchanged_exam.json()["total_marks"] == 10


def test_autonomous_exam_patterns_save_with_required_question_and_co_structure():
    headers = _headers()
    context = _exam_context(headers)
    cases = [
        ("AUTONOMOUS_INTERNAL_1", ["CO1", "CO2"], [(5, 2), (2, 13), (1, 14)], 8, 50),
        ("AUTONOMOUS_INTERNAL_2", ["CO2", "CO3"], [(5, 2), (2, 13), (1, 14)], 8, 50),
        ("AUTONOMOUS_MODEL", ["CO1", "CO2", "CO3", "CO4", "CO5"], [(10, 2), (5, 13), (1, 15)], 16, 100),
    ]

    for exam_type, covered_cos, groups, expected_questions, expected_marks in cases:
        questions = []
        for quantity, marks in groups:
            for _ in range(quantity):
                questions.append({
                    "question_number": f"Q{len(questions) + 1}",
                    "max_marks": marks,
                    "co_code": covered_cos[(len(questions)) % len(covered_cos)],
                })
        response = client.post(
            "/api/exams",
            json={
                "name": f"{exam_type} {uuid4()}",
                "exam_type": exam_type,
                "exam_date": "2026-10-04",
                **context,
                "pass_percentage": 50,
                "covered_cos": covered_cos,
                "questions": questions,
            },
            headers=headers,
        )
        assert response.status_code == 201
        saved_exam = response.json()
        assert saved_exam["exam_type"] == exam_type
        assert saved_exam["total_questions"] == expected_questions
        assert saved_exam["total_marks"] == expected_marks
        assert {question["co_code"] for question in saved_exam["questions"]} == set(covered_cos)
