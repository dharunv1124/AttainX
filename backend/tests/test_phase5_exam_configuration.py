"""
Phase 5 Automated Test Suite: Exam Workspace and Exam Configuration.
Strictly tests:
1. Create exam successfully.
2. Retrieve exam.
3. Update exam.
4. Select multiple covered COs.
5. Reject empty covered CO selection.
6. Save valid pass percentage.
7. Reject invalid pass percentage (<= 0 or > 100).
8. Create questions.
9. Reject duplicate question numbers.
10. Reject question without CO.
11. Reject question mapped to uncovered CO.
12. Reject invalid maximum marks.
13. Correctly store question-to-CO mappings.
14. Correctly associate exam with selected class.
15. Correctly associate exam with subject.
16. Verify subject does not determine student membership.
17. Validate Internal 1 structure.
18. Validate Internal 2 structure.
19. Validate Model structure using confirmed current pattern.
20. Open an existing exam and retrieve its configuration.
"""

import os
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _get_auth_headers():
    resp = client.post(
        "/api/auth/login",
        json={"username": "faculty1", "password": os.environ["OBE_SEED_FACULTY_PASSWORD"]},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _get_class_and_subject_context(headers):
    # Retrieve CSE department
    depts = client.get("/api/departments", headers=headers).json()
    cse = next(d for d in depts if d["code"] == "CSE")

    # Retrieve 3rd Year
    years = client.get("/api/academic/years", headers=headers).json()
    year_3 = next(y for y in years if y["year_number"] == 3)

    # Retrieve Semester 6
    semesters = client.get(f"/api/academic/semesters?year_id={year_3['id']}", headers=headers).json()
    sem_6 = next(s for s in semesters if s["semester_number"] == 6)

    # Retrieve Section A
    sections = client.get(
        f"/api/academic/sections?department_id={cse['id']}&year_id={year_3['id']}",
        headers=headers,
    ).json()
    sec_a = next(s for s in sections if s["name"] == "A")

    # Retrieve a Subject scoped to this Department, Year, and Semester.
    subjects = client.get(
        f"/api/subjects?department_id={cse['id']}&year_id={year_3['id']}&semester_id={sem_6['id']}",
        headers=headers,
    ).json()
    web_technologies = next(s for s in subjects if s["name"] == "WEB TECHNOLOGIES")

    return {
        "department_id": cse["id"],
        "year_id": year_3["id"],
        "semester_id": sem_6["id"],
        "section_id": sec_a["id"],
        "subject_id": web_technologies["id"],
    }


# 1. Create exam successfully
def test_1_create_exam_successfully():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    payload = {
        "name": "Midterm Assessment 1",
        "exam_type": "CUSTOM",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 50.0,
        "covered_cos": ["CO1", "CO2"],
        "questions": [
            {"question_number": "Q1", "max_marks": 5.0, "co_code": "CO1"},
            {"question_number": "Q2", "max_marks": 5.0, "co_code": "CO2"},
        ],
    }

    resp = client.post("/api/exams", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Midterm Assessment 1"
    assert data["exam_date"] == "2026-10-04"
    assert data["pass_percentage"] == 50.0
    assert "CO1" in data["covered_cos"]
    assert "CO2" in data["covered_cos"]
    assert len(data["questions"]) == 2
    assert data["total_marks"] == 10.0
    assert data["total_questions"] == 2


def test_create_requires_a_valid_exam_date():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)
    payload = {
        "name": "Exam Date Validation",
        "exam_type": "CUSTOM",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 50.0,
        "covered_cos": ["CO1"],
        "questions": [{"question_number": "Q1", "max_marks": 10.0, "co_code": "CO1"}],
    }

    assert client.post("/api/exams", json=payload, headers=headers).status_code == 422
    payload["exam_date"] = "2026-02-30"
    assert client.post("/api/exams", json=payload, headers=headers).status_code == 422


def test_same_section_supports_distinct_semester_exams():
    headers = _get_auth_headers()
    context = _get_class_and_subject_context(headers)
    semesters = client.get(
        f"/api/academic/semesters?year_id={context['year_id']}",
        headers=headers,
    ).json()
    semester_ids = {semester["semester_number"]: semester["id"] for semester in semesters}

    def create_for_semester(number):
        subjects = client.get(
            f"/api/subjects?department_id={context['department_id']}&year_id={context['year_id']}"
            f"&semester_id={semester_ids[number]}",
            headers=headers,
        ).json()
        subject_name = "DATABASE SYSTEM" if number == 5 else "WEB TECHNOLOGIES"
        subject = next(item for item in subjects if item["name"] == subject_name)
        return client.post(
            "/api/exams",
            json={
                "name": f"R3 Shared Section Semester {number}",
                "exam_type": "CUSTOM",
                "exam_date": "2026-10-04",
                "department_id": context["department_id"],
                "year_id": context["year_id"],
                "semester_id": semester_ids[number],
                "section_id": context["section_id"],
                "subject_id": subject["id"],
                "pass_percentage": 50.0,
                "covered_cos": ["CO1"],
                "questions": [{"question_number": "Q1", "max_marks": 10.0, "co_code": "CO1"}],
            },
            headers=headers,
        )

    semester_5_exam = create_for_semester(5)
    semester_6_exam = create_for_semester(6)

    assert semester_5_exam.status_code == 201
    assert semester_6_exam.status_code == 201
    assert semester_5_exam.json()["section_id"] == semester_6_exam.json()["section_id"]
    assert semester_5_exam.json()["subject_id"] != semester_6_exam.json()["subject_id"]
    assert semester_5_exam.json()["semester_id"] == semester_ids[5]
    assert semester_6_exam.json()["semester_id"] == semester_ids[6]


# 2. Retrieve exam
def test_2_retrieve_exam():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    # First list to get created exam
    list_resp = client.get(
        f"/api/exams?department_id={ctx['department_id']}&year_id={ctx['year_id']}"
        f"&semester_id={ctx['semester_id']}&section_id={ctx['section_id']}"
        f"&subject_id={ctx['subject_id']}",
        headers=headers,
    )
    assert list_resp.status_code == 200
    exams = list_resp.json()
    assert len(exams) >= 1
    exam_id = exams[0]["id"]

    get_resp = client.get(f"/api/exams/{exam_id}", headers=headers)
    assert get_resp.status_code == 200
    detail = get_resp.json()
    assert detail["id"] == exam_id
    assert detail["department_name"] == "Computer Science and Engineering"
    assert detail["subject_id"] == ctx["subject_id"]
    assert detail["subject_name"] == "WEB TECHNOLOGIES"


# 3. Update exam
def test_3_update_exam():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    payload = {
        "name": "Exam to be Updated",
        "exam_type": "CUSTOM",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 45.0,
        "covered_cos": ["CO1"],
        "questions": [
            {"question_number": "Q1", "max_marks": 10.0, "co_code": "CO1"},
        ],
    }
    create_resp = client.post("/api/exams", json=payload, headers=headers)
    assert create_resp.status_code == 201
    exam_id = create_resp.json()["id"]

    # Update pass percentage and name
    update_payload = {
        "name": "Updated Exam Name",
        "exam_date": "2026-10-05",
        "pass_percentage": 55.0,
    }
    update_resp = client.put(f"/api/exams/{exam_id}", json=update_payload, headers=headers)
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["name"] == "Updated Exam Name"
    assert data["exam_date"] == "2026-10-05"
    assert data["pass_percentage"] == 55.0


def test_exam_update_duplicate_validation_excludes_current_exam_only():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)
    subjects = client.get(
        f"/api/subjects?department_id={ctx['department_id']}&year_id={ctx['year_id']}"
        f"&semester_id={ctx['semester_id']}",
        headers=headers,
    ).json()
    other_subject = next(subject for subject in subjects if subject["id"] != ctx["subject_id"])
    sections = client.get(
        f"/api/academic/sections?department_id={ctx['department_id']}&year_id={ctx['year_id']}",
        headers=headers,
    ).json()
    section_b = next(section for section in sections if section["name"] == "B")

    def create(name, subject_id=ctx["subject_id"], section_id=ctx["section_id"]):
        return client.post(
            "/api/exams",
            json={
                "name": name,
                "exam_type": "CUSTOM",
                "exam_date": "2026-10-04",
                "department_id": ctx["department_id"],
                "year_id": ctx["year_id"],
                "semester_id": ctx["semester_id"],
                "section_id": section_id,
                "subject_id": subject_id,
                "pass_percentage": 50.0,
                "covered_cos": ["CO1"],
                "questions": [{"question_number": "Q1", "max_marks": 10.0, "co_code": "CO1"}],
            },
            headers=headers,
        )

    exam_a = create("Edit Validation Exam A")
    exam_b = create("Edit Validation Exam B")
    assert exam_a.status_code == 201
    assert exam_b.status_code == 201
    exam_a_id = exam_a.json()["id"]

    unchanged_name = client.put(
        f"/api/exams/{exam_a_id}",
        json={"name": "Edit Validation Exam A"},
        headers=headers,
    )
    assert unchanged_name.status_code == 200

    changed_configuration = client.put(
        f"/api/exams/{exam_a_id}",
        json={
            "name": "Edit Validation Exam A",
            "pass_percentage": 60.0,
            "questions": [{"question_number": "Q1", "max_marks": 20.0, "co_code": "CO1"}],
        },
        headers=headers,
    )
    assert changed_configuration.status_code == 200
    assert changed_configuration.json()["pass_percentage"] == 60.0
    assert changed_configuration.json()["questions"][0]["max_marks"] == 20.0

    duplicate_create = create("Edit Validation Exam A")
    assert duplicate_create.status_code == 400
    assert "already exists" in duplicate_create.json()["detail"]

    duplicate_update = client.put(
        f"/api/exams/{exam_a_id}",
        json={"name": "Edit Validation Exam B"},
        headers=headers,
    )
    assert duplicate_update.status_code == 400

    assert create("Edit Validation Exam A", subject_id=other_subject["id"]).status_code == 201
    assert create("Edit Validation Exam A", section_id=section_b["id"]).status_code == 201


# 4. Select multiple covered COs
def test_4_select_multiple_covered_cos():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    payload = {
        "name": "Multi-CO Exam",
        "exam_type": "CUSTOM",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 50.0,
        "covered_cos": ["CO1", "CO2", "CO3", "CO4"],
        "questions": [
            {"question_number": "Q1", "max_marks": 5.0, "co_code": "CO1"},
            {"question_number": "Q2", "max_marks": 5.0, "co_code": "CO2"},
            {"question_number": "Q3", "max_marks": 5.0, "co_code": "CO3"},
            {"question_number": "Q4", "max_marks": 5.0, "co_code": "CO4"},
        ],
    }
    resp = client.post("/api/exams", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert set(data["covered_cos"]) == {"CO1", "CO2", "CO3", "CO4"}


# 5. Reject empty covered CO selection
def test_5_reject_empty_covered_co_selection():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    payload = {
        "name": "Empty CO Exam",
        "exam_type": "CUSTOM",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 50.0,
        "covered_cos": [],
        "questions": [
            {"question_number": "Q1", "max_marks": 5.0, "co_code": "CO1"},
        ],
    }
    resp = client.post("/api/exams", json=payload, headers=headers)
    assert resp.status_code in (400, 422)


# 6. Save valid pass percentage
def test_6_save_valid_pass_percentage():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    payload = {
        "name": "Pass Percentage Test",
        "exam_type": "CUSTOM",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 65.5,
        "covered_cos": ["CO1"],
        "questions": [
            {"question_number": "Q1", "max_marks": 20.0, "co_code": "CO1"},
        ],
    }
    resp = client.post("/api/exams", json=payload, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["pass_percentage"] == 65.5


# 7. Reject invalid pass percentage
def test_7_reject_invalid_pass_percentage():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    # 0 or negative
    payload = {
        "name": "Invalid Pass Pct",
        "exam_type": "CUSTOM",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 0.0,
        "covered_cos": ["CO1"],
        "questions": [{"question_number": "Q1", "max_marks": 10.0, "co_code": "CO1"}],
    }
    resp = client.post("/api/exams", json=payload, headers=headers)
    assert resp.status_code in (400, 422)

    # > 100
    payload["pass_percentage"] = 105.0
    resp = client.post("/api/exams", json=payload, headers=headers)
    assert resp.status_code in (400, 422)


# 8. Create questions
def test_8_create_questions():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    payload = {
        "name": "Question Creation Exam",
        "exam_type": "CUSTOM",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 50.0,
        "covered_cos": ["CO1", "CO2"],
        "questions": [
            {"question_number": "1", "max_marks": 2.0, "co_code": "CO1"},
            {"question_number": "2", "max_marks": 2.0, "co_code": "CO1"},
            {"question_number": "3", "max_marks": 10.0, "co_code": "CO2"},
        ],
    }
    resp = client.post("/api/exams", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["questions"]) == 3
    assert data["total_marks"] == 14.0


# 9. Reject duplicate question numbers
def test_9_reject_duplicate_question_numbers():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    payload = {
        "name": "Duplicate Question Test",
        "exam_type": "CUSTOM",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 50.0,
        "covered_cos": ["CO1"],
        "questions": [
            {"question_number": "Q1", "max_marks": 5.0, "co_code": "CO1"},
            {"question_number": "Q1", "max_marks": 5.0, "co_code": "CO1"},  # duplicate
        ],
    }
    resp = client.post("/api/exams", json=payload, headers=headers)
    assert resp.status_code == 400
    assert "Duplicate question number" in resp.json()["detail"]


# 10. Reject question without CO
def test_10_reject_question_without_co():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    payload = {
        "name": "Missing CO on Question",
        "exam_type": "CUSTOM",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 50.0,
        "covered_cos": ["CO1"],
        "questions": [
            {"question_number": "Q1", "max_marks": 5.0, "co_code": ""},
        ],
    }
    resp = client.post("/api/exams", json=payload, headers=headers)
    assert resp.status_code in (400, 422)


# 11. Reject question mapped to uncovered CO
def test_11_reject_question_mapped_to_uncovered_co():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    # Covered CO is CO1, but Question is mapped to CO3
    payload = {
        "name": "Uncovered CO Question Exam",
        "exam_type": "CUSTOM",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 50.0,
        "covered_cos": ["CO1"],
        "questions": [
            {"question_number": "Q1", "max_marks": 5.0, "co_code": "CO3"},
        ],
    }
    resp = client.post("/api/exams", json=payload, headers=headers)
    assert resp.status_code == 400
    assert "NOT in the exam's covered CO list" in resp.json()["detail"]


# 12. Reject invalid maximum marks
def test_12_reject_invalid_maximum_marks():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    payload = {
        "name": "Zero Max Mark Question",
        "exam_type": "CUSTOM",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 50.0,
        "covered_cos": ["CO1"],
        "questions": [
            {"question_number": "Q1", "max_marks": 0.0, "co_code": "CO1"},
        ],
    }
    resp = client.post("/api/exams", json=payload, headers=headers)
    assert resp.status_code in (400, 422)


# 13. Correctly store question-to-CO mappings
def test_13_correctly_store_question_to_co_mappings():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    payload = {
        "name": "Mapping Verification Exam",
        "exam_type": "CUSTOM",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 50.0,
        "covered_cos": ["CO1", "CO2"],
        "questions": [
            {"question_number": "Q1", "max_marks": 2.0, "co_code": "CO1"},
            {"question_number": "Q2", "max_marks": 2.0, "co_code": "CO1"},
            {"question_number": "Q3", "max_marks": 10.0, "co_code": "CO2"},
        ],
    }
    resp = client.post("/api/exams", json=payload, headers=headers)
    assert resp.status_code == 201
    exam_id = resp.json()["id"]

    fetch_resp = client.get(f"/api/exams/{exam_id}", headers=headers)
    q_map = {q["question_number"]: q["co_code"] for q in fetch_resp.json()["questions"]}
    assert q_map["Q1"] == "CO1"
    assert q_map["Q2"] == "CO1"
    assert q_map["Q3"] == "CO2"


# 14. Correctly associate exam with selected class
def test_14_correctly_associate_exam_with_selected_class():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    payload = {
        "name": "Class Association Exam",
        "exam_type": "CUSTOM",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 50.0,
        "covered_cos": ["CO1"],
        "questions": [
            {"question_number": "Q1", "max_marks": 5.0, "co_code": "CO1"},
        ],
    }
    resp = client.post("/api/exams", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["department_id"] == ctx["department_id"]
    assert data["year_id"] == ctx["year_id"]
    assert data["semester_id"] == ctx["semester_id"]
    assert data["section_id"] == ctx["section_id"]
    assert data["section_name"] == "A"


# 15. Correctly associate exam with subject
def test_15_correctly_associate_exam_with_subject():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    payload = {
        "name": "Subject Association Exam",
        "exam_type": "CUSTOM",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 50.0,
        "covered_cos": ["CO1"],
        "questions": [
            {"question_number": "Q1", "max_marks": 5.0, "co_code": "CO1"},
        ],
    }
    resp = client.post("/api/exams", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["subject_id"] == ctx["subject_id"]
    assert data["subject_name"] == "WEB TECHNOLOGIES"


# 16. Verify subject does not determine student membership
def test_16_verify_subject_does_not_determine_student_membership():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    # In Phase 4 we seeded 5 students in Section A
    # The exam detail response provides student_count derived purely from Section A
    payload = {
        "name": "Cohort Independence Exam",
        "exam_type": "CUSTOM",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 50.0,
        "covered_cos": ["CO1"],
        "questions": [
            {"question_number": "Q1", "max_marks": 5.0, "co_code": "CO1"},
        ],
    }
    resp = client.post("/api/exams", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    # Student count must match Section A cohort
    assert data["student_count"] >= 5

    # Check student roster endpoint from section: students have NO subject_id attribute
    students_resp = client.get(f"/api/sections/{ctx['section_id']}/students", headers=headers)
    for st in students_resp.json():
        assert "subject_id" not in st
        assert st["section_id"] == ctx["section_id"]


def test_16a_same_section_roster_is_available_across_subjects():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)
    subjects = client.get(
        f"/api/subjects?department_id={ctx['department_id']}&year_id={ctx['year_id']}"
        f"&semester_id={ctx['semester_id']}",
        headers=headers,
    ).json()
    second_subject = next(subject for subject in subjects if subject["id"] != ctx["subject_id"])

    def create_exam(subject_id, name):
        return client.post(
            "/api/exams",
            json={
                "name": name,
                "exam_type": "CUSTOM",
                "exam_date": "2026-10-04",
                "department_id": ctx["department_id"],
                "year_id": ctx["year_id"],
                "semester_id": ctx["semester_id"],
                "section_id": ctx["section_id"],
                "subject_id": subject_id,
                "pass_percentage": 50.0,
                "covered_cos": ["CO1"],
                "questions": [{"question_number": "Q1", "max_marks": 5.0, "co_code": "CO1"}],
            },
            headers=headers,
        )

    first = create_exam(ctx["subject_id"], "Shared Roster Subject One")
    second = create_exam(second_subject["id"], "Shared Roster Subject Two")
    assert first.status_code == 201
    assert second.status_code == 201

    first_roster = client.get(f"/api/exams/{first.json()['id']}/roster", headers=headers)
    second_roster = client.get(f"/api/exams/{second.json()['id']}/roster", headers=headers)
    assert first_roster.status_code == 200
    assert second_roster.status_code == 200
    assert {student["register_no"] for student in first_roster.json()} == {
        student["register_no"] for student in second_roster.json()
    }


def test_subject_filtered_exams_keep_subject_identity():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)
    target_subjects = client.get(
        f"/api/subjects?department_id={ctx['department_id']}&year_id={ctx['year_id']}"
        f"&semester_id={ctx['semester_id']}",
        headers=headers,
    ).json()
    assert {subject["name"] for subject in target_subjects} >= {
        "WEB TECHNOLOGIES",
        "COMPILER DESIGN",
        "DISTRIBUTED COMPUTING SYSTEM",
        "ARTIFICIAL INTELLIGENCE AND MACHINE LEARNING",
    }

    for subject in target_subjects:
        payload = {
            "name": f"Subject Identity {subject['id']}",
            "exam_type": "CUSTOM",
            "exam_date": "2026-10-04",
            "department_id": ctx["department_id"],
            "year_id": ctx["year_id"],
            "semester_id": ctx["semester_id"],
            "section_id": ctx["section_id"],
            "subject_id": subject["id"],
            "pass_percentage": 50.0,
            "covered_cos": ["CO1"],
            "questions": [{"question_number": "Q1", "max_marks": 10.0, "co_code": "CO1"}],
        }
        response = client.post("/api/exams", json=payload, headers=headers)
        assert response.status_code == 201

        filtered = client.get(
            f"/api/exams?section_id={ctx['section_id']}&subject_id={subject['id']}",
            headers=headers,
        )
        assert filtered.status_code == 200
        assert all(exam["subject_id"] == subject["id"] for exam in filtered.json())

    for subject in target_subjects:
        assert subject["department_id"] == ctx["department_id"]
        assert subject["year_id"] == ctx["year_id"]
        assert subject["semester_id"] == ctx["semester_id"]


def test_16b_duplicate_exam_name_is_rejected_for_same_class_and_subject():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)
    payload = {
        "name": "Duplicate Internal Assessment 1 Guard",
        "exam_type": "CUSTOM",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 50.0,
        "covered_cos": ["CO1"],
        "questions": [{"question_number": "Q1", "max_marks": 5.0, "co_code": "CO1"}],
    }
    first = client.post("/api/exams", json=payload, headers=headers)
    duplicate = client.post("/api/exams", json=payload, headers=headers)
    assert first.status_code == 201
    assert duplicate.status_code == 400
    assert "already exists" in duplicate.json()["detail"]


# 17. Validate Internal 1 structure (10 x 2m + 3 x 10m = 50 marks)
def test_17_validate_internal_1_structure():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    # Valid Internal 1 structure
    valid_questions = [
        {"question_number": f"Q{i}", "max_marks": 2.0, "co_code": "CO1" if i <= 5 else "CO2"}
        for i in range(1, 11)
    ] + [
        {"question_number": "Q11", "max_marks": 10.0, "co_code": "CO1"},
        {"question_number": "Q12", "max_marks": 10.0, "co_code": "CO2"},
        {"question_number": "Q13", "max_marks": 10.0, "co_code": "CO1"},
    ]

    valid_payload = {
        "name": "Internal Assessment 1",
        "exam_type": "INTERNAL_1",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 50.0,
        "covered_cos": ["CO1", "CO2"],
        "questions": valid_questions,
    }
    resp = client.post("/api/exams", json=valid_payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["total_marks"] == 50.0
    assert data["total_questions"] == 13

    # Invalid Internal 1 (wrong marks count: e.g. 12 questions or 40 marks)
    invalid_payload = dict(valid_payload)
    invalid_payload["questions"] = valid_questions[:12]
    bad_resp = client.post("/api/exams", json=invalid_payload, headers=headers)
    assert bad_resp.status_code == 400
    assert "Pattern mismatch for INTERNAL_1" in bad_resp.json()["detail"]


# 18. Validate Internal 2 structure (10 x 2m + 3 x 10m = 50 marks)
def test_18_validate_internal_2_structure():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    valid_questions = [
        {"question_number": f"Q{i}", "max_marks": 2.0, "co_code": "CO3" if i <= 5 else "CO4"}
        for i in range(1, 11)
    ] + [
        {"question_number": "Q11", "max_marks": 10.0, "co_code": "CO3"},
        {"question_number": "Q12", "max_marks": 10.0, "co_code": "CO4"},
        {"question_number": "Q13", "max_marks": 10.0, "co_code": "CO3"},
    ]

    valid_payload = {
        "name": "Internal Assessment 2",
        "exam_type": "INTERNAL_2",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 50.0,
        "covered_cos": ["CO3", "CO4"],
        "questions": valid_questions,
    }
    resp = client.post("/api/exams", json=valid_payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["total_marks"] == 50.0
    assert data["total_questions"] == 13


# 19. Validate Model structure using confirmed current pattern (10 x 2m + 5 x 8m = 60 marks)
def test_19_validate_model_structure_confirmed_pattern():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    # 10 x 2m + 5 x 8m = 60 marks (15 questions)
    valid_questions = [
        {"question_number": f"Q{i}", "max_marks": 2.0, "co_code": f"CO{(i % 5) + 1}"}
        for i in range(1, 11)
    ] + [
        {"question_number": f"Q{10 + i}", "max_marks": 8.0, "co_code": f"CO{i}"}
        for i in range(1, 6)
    ]

    valid_payload = {
        "name": "Model Examination",
        "exam_type": "MODEL",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 50.0,
        "covered_cos": ["CO1", "CO2", "CO3", "CO4", "CO5"],
        "questions": valid_questions,
    }
    resp = client.post("/api/exams", json=valid_payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["total_marks"] == 60.0
    assert data["total_questions"] == 15

    # Invalid Model exam (wrong total marks)
    invalid_questions = list(valid_questions)
    invalid_questions[0] = {"question_number": "Q1", "max_marks": 5.0, "co_code": "CO1"}
    bad_payload = dict(valid_payload)
    bad_payload["questions"] = invalid_questions
    bad_resp = client.post("/api/exams", json=bad_payload, headers=headers)
    assert bad_resp.status_code == 400
    assert "Pattern mismatch for MODEL" in bad_resp.json()["detail"]


# 20. Open an existing exam and retrieve its configuration
def test_20_open_existing_exam_and_retrieve_configuration():
    headers = _get_auth_headers()
    ctx = _get_class_and_subject_context(headers)

    # Create exam
    payload = {
        "name": "Exam to be Reopened in Workspace",
        "exam_type": "CUSTOM",
        "exam_date": "2026-10-04",
        "department_id": ctx["department_id"],
        "year_id": ctx["year_id"],
        "semester_id": ctx["semester_id"],
        "section_id": ctx["section_id"],
        "subject_id": ctx["subject_id"],
        "pass_percentage": 50.0,
        "covered_cos": ["CO1", "CO2"],
        "questions": [
            {"question_number": "Q1", "max_marks": 5.0, "co_code": "CO1"},
            {"question_number": "Q2", "max_marks": 15.0, "co_code": "CO2"},
        ],
    }
    create_resp = client.post("/api/exams", json=payload, headers=headers)
    assert create_resp.status_code == 201
    created_id = create_resp.json()["id"]

    # Reopen exam workspace
    open_resp = client.get(f"/api/exams/{created_id}", headers=headers)
    assert open_resp.status_code == 200
    workspace_data = open_resp.json()

    assert workspace_data["id"] == created_id
    assert workspace_data["name"] == "Exam to be Reopened in Workspace"
    assert workspace_data["department_name"] == "Computer Science and Engineering"
    assert workspace_data["year_name"] == "3rd Year"
    assert workspace_data["semester_name"] == "Semester 6"
    assert workspace_data["section_name"] == "A"
    assert workspace_data["subject_name"] == "WEB TECHNOLOGIES"
    assert workspace_data["pass_percentage"] == 50.0
    assert workspace_data["covered_cos"] == ["CO1", "CO2"]
    assert len(workspace_data["questions"]) == 2
    assert workspace_data["total_marks"] == 20.0
