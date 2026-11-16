import os

from fastapi.testclient import TestClient
from app.main import app
from app.db.models import Batch, Subject
from app.db.session import SessionLocal
from app.seeds.dev_seed import seed_database

client = TestClient(app)


def _headers():
    resp = client.post(
        "/api/auth/login",
        json={"username": "faculty1", "password": os.environ["OBE_SEED_FACULTY_PASSWORD"]},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_locked_subject_catalog_for_cse_3rd_year():
    headers = _headers()
    depts = client.get("/api/departments", headers=headers).json()
    cse = next(d for d in depts if d["code"] == "CSE")
    years = client.get("/api/academic/years", headers=headers).json()
    year_3 = next(y for y in years if y["year_number"] == 3)
    semesters = client.get(f"/api/academic/semesters?year_id={year_3['id']}", headers=headers).json()
    sem_5 = next(s for s in semesters if s["semester_number"] == 5)
    sem_6 = next(s for s in semesters if s["semester_number"] == 6)

    sem_5_subjects = client.get(
        f"/api/subjects?department_id={cse['id']}&year_id={year_3['id']}&semester_id={sem_5['id']}",
        headers=headers,
    ).json()
    sem_6_subjects = client.get(
        f"/api/subjects?department_id={cse['id']}&year_id={year_3['id']}&semester_id={sem_6['id']}",
        headers=headers,
    ).json()

    assert [s["name"] for s in sem_5_subjects] == [
        "COMPUTER NETWORKS",
        "DATABASE SYSTEM",
        "OPERATING SYSTEM",
        "SOFTWARE ENGINEERING",
        "THEORY OF COMPUTATION",
    ]
    assert [s["name"] for s in sem_6_subjects] == [
        "ARTIFICIAL INTELLIGENCE AND MACHINE LEARNING",
        "COMPILER DESIGN",
        "DISTRIBUTED COMPUTING SYSTEM",
        "WEB TECHNOLOGIES",
    ]


def test_section_independence_and_semester_switch():
    headers = _headers()
    depts = client.get("/api/departments", headers=headers).json()
    cse = next(d for d in depts if d["code"] == "CSE")
    years = client.get("/api/academic/years", headers=headers).json()
    year_3 = next(y for y in years if y["year_number"] == 3)
    semesters = client.get(f"/api/academic/semesters?year_id={year_3['id']}", headers=headers).json()
    sem_5 = next(s for s in semesters if s["semester_number"] == 5)
    sem_6 = next(s for s in semesters if s["semester_number"] == 6)
    sections = client.get(f"/api/academic/sections?department_id={cse['id']}&year_id={year_3['id']}", headers=headers).json()

    sem_5_by_section = {
        section["name"]: client.get(
            f"/api/subjects?department_id={cse['id']}&year_id={year_3['id']}&semester_id={sem_5['id']}",
            headers=headers,
        ).json()
        for section in sections
    }
    sem_6_by_section = {
        section["name"]: client.get(
            f"/api/subjects?department_id={cse['id']}&year_id={year_3['id']}&semester_id={sem_6['id']}",
            headers=headers,
        ).json()
        for section in sections
    }

    subject_names_5 = {tuple(s["name"] for s in values) for values in sem_5_by_section.values()}
    subject_names_6 = {tuple(s["name"] for s in values) for values in sem_6_by_section.values()}
    assert len(subject_names_5) == 1
    assert len(subject_names_6) == 1

    section_a_students = client.get(f"/api/sections/{next(s for s in sections if s['name'] == 'A')['id']}/students", headers=headers).json()
    assert len(section_a_students) == 5
    assert {s["register_no"] for s in section_a_students} == {
        "TEST-REG-0001",
        "TEST-REG-0002",
        "TEST-REG-0003",
        "TEST-REG-0004",
        "TEST-REG-0005",
    }


def test_seed_removes_incorrect_semester_6_scopes_without_deleting_subjects():
    headers = _headers()
    depts = client.get("/api/departments", headers=headers).json()
    cse = next(department for department in depts if department["code"] == "CSE")
    years = client.get("/api/academic/years", headers=headers).json()
    year_3 = next(year for year in years if year["year_number"] == 3)
    semesters = client.get(f"/api/academic/semesters?year_id={year_3['id']}", headers=headers).json()
    semester_6 = next(semester for semester in semesters if semester["semester_number"] == 6)
    wrong_names = {"DATABASE MANAGEMENT SYSTEMS", "THEORY OF COMPUTATION"}

    with SessionLocal() as db:
        batch = db.query(Batch).filter_by(start_year=2024, end_year=2028).one()
        inserted_subject_ids = {}
        for name in wrong_names:
            subject = Subject(
                name=name,
                batch_id=batch.id,
                department_id=cse["id"],
                year_id=year_3["id"],
                semester_id=semester_6["id"],
            )
            db.add(subject)
            db.flush()
            inserted_subject_ids[name] = subject.id
        db.commit()
        seed_database(db)
        preserved_subjects = db.query(Subject).filter(Subject.id.in_(inserted_subject_ids.values())).all()
        assert {subject.name for subject in preserved_subjects} == wrong_names
        assert all(
            subject.department_id is None and subject.year_id is None and subject.semester_id is None
            for subject in preserved_subjects
        )

    semester_5 = next(semester for semester in semesters if semester["semester_number"] == 5)
    for semester, expected in (
        (semester_5, {
            "DATABASE SYSTEM",
            "COMPUTER NETWORKS",
            "OPERATING SYSTEM",
            "THEORY OF COMPUTATION",
            "SOFTWARE ENGINEERING",
        }),
        (semester_6, {
            "WEB TECHNOLOGIES",
            "COMPILER DESIGN",
            "DISTRIBUTED COMPUTING SYSTEM",
            "ARTIFICIAL INTELLIGENCE AND MACHINE LEARNING",
        }),
    ):
        response = client.get(
            f"/api/subjects?department_id={cse['id']}&year_id={year_3['id']}&semester_id={semester['id']}",
            headers=headers,
        )
        assert response.status_code == 200
        assert {subject["name"] for subject in response.json()} == expected
        assert len(response.json()) == len(expected)


def test_subject_to_exam_filter_keeps_subject_identity():
    headers = _headers()
    depts = client.get("/api/departments", headers=headers).json()
    cse = next(d for d in depts if d["code"] == "CSE")
    years = client.get("/api/academic/years", headers=headers).json()
    year_3 = next(y for y in years if y["year_number"] == 3)
    semesters = client.get(f"/api/academic/semesters?year_id={year_3['id']}", headers=headers).json()
    sem_5 = next(s for s in semesters if s["semester_number"] == 5)
    sections = client.get(f"/api/academic/sections?department_id={cse['id']}&year_id={year_3['id']}", headers=headers).json()
    section_a = next(s for s in sections if s["name"] == "A")

    subjects = client.get(
        f"/api/subjects?department_id={cse['id']}&year_id={year_3['id']}&semester_id={sem_5['id']}",
        headers=headers,
    ).json()

    for subject in subjects:
        payload = {
            "name": f"R5 Subject {subject['id']}",
            "exam_type": "CUSTOM",
            "exam_date": "2026-10-04",
            "department_id": cse["id"],
            "year_id": year_3["id"],
            "semester_id": sem_5["id"],
            "section_id": section_a["id"],
            "subject_id": subject["id"],
            "pass_percentage": 50.0,
            "covered_cos": ["CO1"],
            "questions": [{"question_number": "Q1", "max_marks": 10.0, "co_code": "CO1"}],
        }
        exam_resp = client.post("/api/exams", json=payload, headers=headers)
        assert exam_resp.status_code == 201

        filtered = client.get(
            f"/api/exams?department_id={cse['id']}&year_id={year_3['id']}&semester_id={sem_5['id']}&section_id={section_a['id']}&subject_id={subject['id']}",
            headers=headers,
        ).json()
        assert filtered
        assert all(exam["subject_id"] == subject["id"] for exam in filtered)


def test_exam_context_matches_selected_department_year_semester_section_subject():
    headers = _headers()
    depts = client.get("/api/departments", headers=headers).json()
    cse = next(d for d in depts if d["code"] == "CSE")
    years = client.get("/api/academic/years", headers=headers).json()
    year_3 = next(y for y in years if y["year_number"] == 3)
    semesters = client.get(f"/api/academic/semesters?year_id={year_3['id']}", headers=headers).json()
    sem_5 = next(s for s in semesters if s["semester_number"] == 5)
    sections = client.get(f"/api/academic/sections?department_id={cse['id']}&year_id={year_3['id']}", headers=headers).json()
    section_a = next(s for s in sections if s["name"] == "A")
    subjects = client.get(
        f"/api/subjects?department_id={cse['id']}&year_id={year_3['id']}&semester_id={sem_5['id']}",
        headers=headers,
    ).json()
    subject = next(s for s in subjects if s["name"] == "COMPUTER NETWORKS")

    payload = {
        "name": "Computer Networks Context Check",
        "exam_type": "CUSTOM",
        "exam_date": "2026-10-04",
        "department_id": cse["id"],
        "year_id": year_3["id"],
        "semester_id": sem_5["id"],
        "section_id": section_a["id"],
        "subject_id": subject["id"],
        "pass_percentage": 50.0,
        "covered_cos": ["CO1"],
        "questions": [{"question_number": "Q1", "max_marks": 10.0, "co_code": "CO1"}],
    }
    exam = client.post("/api/exams", json=payload, headers=headers)
    assert exam.status_code == 201
    exam_data = exam.json()
    assert exam_data["department_id"] == cse["id"]
    assert exam_data["year_id"] == year_3["id"]
    assert exam_data["semester_id"] == sem_5["id"]
    assert exam_data["section_id"] == section_a["id"]
    assert exam_data["subject_id"] == subject["id"]
