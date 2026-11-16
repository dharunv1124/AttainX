import io
import os
from datetime import datetime, timezone
from uuid import uuid4
from openpyxl import Workbook
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from fastapi.testclient import TestClient
from app.main import app
from app.db.models import (
    Exam,
    Section,
    Student,
    StudentAcademicPlacement,
    StudentMark,
    Subject,
)
from app.db.session import SessionLocal
from app.services.student_service import StudentService

client = TestClient(app)


def test_import_routes_use_the_locked_post_contract():
    paths = app.openapi()["paths"]
    assert set(paths["/api/students/import-preview"]) == {"post"}
    assert set(paths["/api/students/import"]) == {"post"}


def _headers():
    resp = client.post(
        "/api/auth/login",
        json={"username": "faculty1", "password": os.environ["OBE_SEED_FACULTY_PASSWORD"]},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _section_context(headers):
    depts = client.get("/api/departments", headers=headers).json()
    cse = next(d for d in depts if d["code"] == "CSE")
    years = client.get("/api/academic/years", headers=headers).json()
    year_3 = next(y for y in years if y["year_number"] == 3)
    sections = client.get(f"/api/academic/sections?department_id={cse['id']}&year_id={year_3['id']}", headers=headers).json()
    section_a = next(s for s in sections if s["name"] == "A")
    return cse, year_3, section_a


def test_section_roster_returns_one_character_register_numbers_and_rejects_empty():
    headers = _headers()
    _, year_3, section_a = _section_context(headers)

    create_response = client.post(
        "/api/students",
        json={"register_no": "1", "name": "ROSTER CHECK", "section_id": section_a["id"]},
        headers=headers,
    )
    assert create_response.status_code == 201, create_response.text

    roster_response = client.get(f"/api/sections/{section_a['id']}/students", headers=headers)
    assert roster_response.status_code == 200, roster_response.text
    roster = roster_response.json()
    register_numbers = {student["register_no"] for student in roster}
    assert "1" in register_numbers
    assert "TEST-REG-0001" in register_numbers
    assert all(student["section_id"] == section_a["id"] for student in roster)
    assert year_3["year_number"] == 3

    empty_register_response = client.post(
        "/api/students",
        json={"register_no": "", "name": "INVALID ROSTER CHECK", "section_id": section_a["id"]},
        headers=headers,
    )
    assert empty_register_response.status_code == 422


def test_successful_csv_import_and_section_roster_update():
    headers = _headers()
    _, _, section_a = _section_context(headers)
    content = "Register Number,Student Name\nTEST-REG-0006,Sample Student 6\nTEST-REG-0007,Sample Student 7\n"
    resp = client.post(
        "/api/students/import-preview",
        files={"file": ("students.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"])},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_rows"] == 2
    assert body["valid_rows"] == 2
    assert body["invalid_rows"] == 0
    assert not body["duplicate_register_numbers"]

    import_resp = client.post(
        "/api/students/import",
        files={"file": ("students.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"]), "confirm": "true"},
        headers=headers,
    )
    assert import_resp.status_code == 200, import_resp.text
    result = import_resp.json()
    assert result["imported_count"] == 2

    roster = client.get(f"/api/sections/{section_a['id']}/students", headers=headers).json()
    register_nos = {student["register_no"] for student in roster}
    assert {"TEST-REG-0006", "TEST-REG-0007"}.issubset(register_nos)


def test_successful_xlsx_import():
    headers = _headers()
    _, _, section_a = _section_context(headers)
    wb = Workbook()
    ws = wb.active
    ws.title = "Students"
    ws.append(["Register Number", "Student Name"])
    ws.append(["TEST-REG-0008", "Sample Student 8"])
    ws.append(["TEST-REG-0009", "Sample Student 9"])
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    resp = client.post(
        "/api/students/import-preview",
        files={"file": ("students.xlsx", stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"section_id": str(section_a["id"])},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["valid_rows"] == 2

    import_resp = client.post(
        "/api/students/import",
        files={"file": ("students.xlsx", stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"section_id": str(section_a["id"]), "confirm": "true"},
        headers=headers,
    )
    assert import_resp.status_code == 200, import_resp.text
    assert import_resp.json()["imported_count"] == 2


def test_college_xlsx_with_title_rows_and_later_header_imports_string_register_numbers():
    headers = _headers()
    _, _, section_a = _section_context(headers)
    wb = Workbook()
    ws = wb.active
    ws.title = "Student List"
    for title in (
        "College Name",
        "Department of Computer Science and Engineering",
        "Student List",
        "Academic Batch: 2026",
        "Class: Third Year",
        "Section: A",
        "Register-wise Student Details",
    ):
        ws.append([title])
    ws.append([" register\u00a0number\u200b ", "STUDENT NAME", "Department", "Year", "Section", "Semester", "Subject"])
    ws.append(["00260312345", "  TAYLOR STUDENT  ", "Ignored Department", "Ignored Year", "Ignored Section", "Ignored Semester", "Ignored Subject"])
    ws.append([None, None, None, None, None, None, None])
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    import_resp = client.post(
        "/api/students/import",
        files={"file": ("college_students.xlsx", stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"section_id": str(section_a["id"]), "confirm": "true"},
        headers=headers,
    )

    assert import_resp.status_code == 200, import_resp.text
    assert import_resp.json()["imported_count"] == 1
    roster = client.get(f"/api/sections/{section_a['id']}/students", headers=headers).json()
    imported = next(student for student in roster if student["register_no"] == "00260312345")
    assert imported["name"] == "TAYLOR STUDENT"


def test_xlsx_without_required_header_returns_exact_missing_columns_error():
    headers = _headers()
    _, _, section_a = _section_context(headers)
    wb = Workbook()
    ws = wb.active
    ws.append(["College Name"])
    ws.append(["Registration", "Name"])
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    resp = client.post(
        "/api/students/import-preview",
        files={"file": ("bad_students.xlsx", stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"section_id": str(section_a["id"])},
        headers=headers,
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Missing required columns: Register Number, Student Name."


def test_xlsx_header_is_found_on_nonactive_worksheet():
    headers = _headers()
    _, _, section_a = _section_context(headers)
    wb = Workbook()
    cover_sheet = wb.active
    cover_sheet.title = "Cover"
    cover_sheet.append(["College Name"])
    student_sheet = wb.create_sheet("Student Data")
    student_sheet.append(["College Name"])
    student_sheet.append(["Register Number", "Student Name"])
    student_sheet.append(["TEST-REG-0031", "SECOND SHEET STUDENT"])
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    resp = client.post(
        "/api/students/import-preview",
        files={"file": ("student_data.xlsx", stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"section_id": str(section_a["id"])},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["valid_rows"] == 1


def test_csv_import_tolerates_leading_blank_rows_and_case_whitespace_in_headers():
    headers = _headers()
    _, _, section_a = _section_context(headers)
    content = "\n\n  register number , STUDENT NAME \nTEST-REG-0030,CASE TEST\n"
    resp = client.post(
        "/api/students/import-preview",
        files={"file": ("students.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"])},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["valid_rows"] == 1


def test_missing_required_columns_is_rejected():
    headers = _headers()
    _, _, section_a = _section_context(headers)
    content = "Registration,Name\nTEST-REG-0010,FRANK MILLER\n"
    resp = client.post(
        "/api/students/import-preview",
        files={"file": ("bad.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"])},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["detail"] == "Missing required columns: Register Number, Student Name."


def test_blank_required_fields_are_detected():
    headers = _headers()
    _, _, section_a = _section_context(headers)
    content = "Register Number,Student Name\n,ALICE\nTEST-REG-0011,\n"
    resp = client.post(
        "/api/students/import-preview",
        files={"file": ("blank.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"])},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["invalid_rows"] == 2
    assert any("Register Number" in message for message in body["errors"])
    assert any("Student Name" in message for message in body["errors"])


def test_duplicate_register_numbers_within_uploaded_file_are_detected():
    headers = _headers()
    _, _, section_a = _section_context(headers)
    content = "Register Number,Student Name\nTEST-REG-0012,ALEX\nTEST-REG-0012,ALICE\n"
    resp = client.post(
        "/api/students/import-preview",
        files={"file": ("duplicate.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"])},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["duplicate_register_numbers"] == ["TEST-REG-0012"]
    assert body["invalid_rows"] == 2


def test_import_treats_student_already_in_selected_section_as_idempotent():
    headers = _headers()
    _, _, section_a = _section_context(headers)
    register_no = "BATCH-IMPORT-CONFLICT"
    created = client.post(
        "/api/students",
        json={"register_no": register_no, "name": "EXISTING STUDENT", "section_id": section_a["id"]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    original_id = created.json()["id"]

    content = f"Register Number,Student Name\n{register_no},existing-student\n"
    preview = client.post(
        "/api/students/import-preview",
        files={"file": ("conflict.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"])},
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["valid_rows"] == 1
    assert preview.json()["already_assigned"] == 1
    assert preview.json()["invalid_rows"] == 0
    assert preview.json()["placement_conflicts"] == 0

    imported = client.post(
        "/api/students/import",
        files={"file": ("conflict.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"]), "confirm": "true"},
        headers=headers,
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["already_assigned_count"] == 1
    assert imported.json()["imported_count"] == 0

    roster = client.get(f"/api/sections/{section_a['id']}/students", headers=headers).json()
    matches = [student for student in roster if student["register_no"] == register_no]
    assert len(matches) == 1
    assert matches[0]["id"] == original_id
    assert matches[0]["name"] == "EXISTING STUDENT"


def test_import_rejects_student_assigned_to_another_active_section():
    headers = _headers()
    _, year_3, section_a = _section_context(headers)
    test_section = client.post(
        "/api/academic/sections",
        headers=headers,
        json={
            "name": f"CONFLICT-{section_a['id']}",
            "batch_id": section_a["batch_id"],
            "department_id": section_a["department_id"],
            "year_id": year_3["id"],
        },
    )
    assert test_section.status_code == 201, test_section.text
    existing_register = f"CONFLICT-REG-{section_a['id']}"
    existing = client.post(
        "/api/students",
        headers=headers,
        json={
            "register_no": existing_register,
            "name": "OTHER SECTION STUDENT",
            "section_id": test_section.json()["id"],
        },
    )
    assert existing.status_code == 201, existing.text
    content = (
        "Register Number,Student Name\n"
        f"{existing_register},OTHER SECTION STUDENT\n"
        f"CONFLICT-NEW-{section_a['id']},NEW STUDENT\n"
    )
    resp = client.post(
        "/api/students/import-preview",
        files={"file": ("conflict.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"])},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["placement_conflicts"] == 1
    assert body["invalid_rows"] == 0
    assert "another Section" in str(body["errors"])

    imported = client.post(
        "/api/students/import",
        files={"file": ("conflict.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"]), "confirm": "true"},
        headers=headers,
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported_count"] == 1
    assert imported.json()["restored_count"] == 0
    assert imported.json()["skipped_conflict_count"] == 1
    assert client.get(
        f"/api/sections/{test_section.json()['id']}/students",
        headers=headers,
    ).json()[0]["id"] == existing.json()["id"]
    target_roster = client.get(
        f"/api/sections/{section_a['id']}/students",
        headers=headers,
    ).json()
    assert any(student["register_no"] == f"CONFLICT-NEW-{section_a['id']}" for student in target_roster)
    assert all(student["id"] != existing.json()["id"] for student in target_roster)


def test_import_restores_eligible_students_and_skips_active_placement_conflicts():
    headers = _headers()
    _, year_3, section_a = _section_context(headers)
    sections = client.get(
        f"/api/academic/sections?batch_id={section_a['batch_id']}",
        headers=headers,
    ).json()
    section_b = next(section for section in sections if section["name"] == "B")
    token = uuid4().hex[:8].upper()
    restorable_students = [
        Student(
            register_no=f"PARTIAL-RESTORE-{token}-{index:02d}",
            name=f"ELIGIBLE RESTORE STUDENT {index:02d}",
            batch_id=section_a["batch_id"],
            section_id=None,
        )
        for index in range(59)
    ]
    conflicting_students = [
        Student(
            register_no=f"PARTIAL-CONFLICT-{token}-{index:02d}",
            name=f"ACTIVE SECTION B STUDENT {index:02d}",
            batch_id=section_a["batch_id"],
            section_id=section_b["id"],
        )
        for index in range(5)
    ]
    with SessionLocal() as db:
        db.add_all([*restorable_students, *conflicting_students])
        db.flush()
        restorable_ids = [student.id for student in restorable_students]
        conflicting_ids = [student.id for student in conflicting_students]
        roster_rows = [
            (student.register_no, student.name)
            for student in [*restorable_students, *conflicting_students]
        ]
        db.add_all([
            StudentAcademicPlacement(
                student_id=student.id,
                batch_id=section_a["batch_id"],
                department_id=section_a["department_id"],
                year_id=year_3["id"],
                section_id=None,
                section_name=None,
                is_current=True,
            )
            for student in restorable_students
        ])
        db.add_all([
            StudentAcademicPlacement(
                student_id=student.id,
                batch_id=section_a["batch_id"],
                department_id=section_a["department_id"],
                year_id=year_3["id"],
                section_id=section_b["id"],
                section_name=section_b["name"],
                is_current=True,
            )
            for student in conflicting_students
        ])
        db.commit()

    content = "Register Number,Student Name\n" + "".join(
        f"{register_no},{name}\n" for register_no, name in roster_rows
    )
    preview = client.post(
        "/api/students/import-preview",
        files={"file": ("partial_restore.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"])},
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["total_rows"] == 64
    assert preview.json()["eligible_for_restoration"] == 59
    assert preview.json()["placement_conflicts"] == 5
    assert preview.json()["invalid_rows"] == 0

    imported = client.post(
        "/api/students/import",
        files={"file": ("partial_restore.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"]), "confirm": "true"},
        headers=headers,
    )
    assert imported.status_code == 200, imported.text
    result = imported.json()
    assert result["restored_count"] == 59
    assert result["imported_count"] == 0
    assert result["skipped_conflict_count"] == 5
    assert "skipped 5 placement conflicts" in result["message"]

    with SessionLocal() as db:
        assert db.query(Student).filter(Student.id.in_(restorable_ids)).count() == 59
        assert db.query(Student).filter(Student.id.in_(conflicting_ids)).count() == 5
        assert db.query(Student).filter(
            Student.id.in_(restorable_ids),
            Student.section_id == section_a["id"],
        ).count() == 59
        assert db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id.in_(restorable_ids),
            StudentAcademicPlacement.is_current.is_(True),
            StudentAcademicPlacement.section_id == section_a["id"],
        ).count() == 59
        assert db.query(Student).filter(
            Student.id.in_(conflicting_ids),
            Student.section_id == section_b["id"],
        ).count() == 5
        assert db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id.in_(conflicting_ids),
            StudentAcademicPlacement.is_current.is_(True),
            StudentAcademicPlacement.section_id == section_b["id"],
        ).count() == 5


def test_restore_repeatedly_after_section_deletion_preserves_identities_and_unrelated_records():
    headers = _headers()
    _, year_3, reference_section = _section_context(headers)
    token = uuid4().hex[:7].upper()
    logical_section_name = f"R{token}"
    sibling_section_name = f"S{token}"

    def create_section(name):
        response = client.post(
            "/api/academic/sections",
            headers=headers,
            json={
                "name": name,
                "batch_id": reference_section["batch_id"],
                "department_id": reference_section["department_id"],
                "year_id": year_3["id"],
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    def upload(endpoint, section_id, content, semester_id):
        return client.post(
            endpoint,
            files={"file": ("restore.csv", content, "text/csv")},
            data={
                "section_id": str(section_id),
                "semester_id": str(semester_id),
                **({"confirm": "true"} if endpoint.endswith("/import") else {}),
            },
            headers=headers,
        )

    target_section = create_section(logical_section_name)
    sibling_section = create_section(sibling_section_name)
    semesters = client.get(
        f"/api/academic/semesters?year_id={year_3['id']}",
        headers=headers,
    ).json()
    semester_5 = next(item for item in semesters if item["semester_number"] == 5)

    student_rows = [
        (f"RST{token}-{number:03d}", f"RESTORE STUDENT {number:03d}")
        for number in range(1, 65)
    ]
    roster_content = "Register Number,Student Name\n" + "".join(
        f"{register_no},{name}\n" for register_no, name in student_rows
    )
    initial_preview = upload(
        "/api/students/import-preview",
        target_section["id"],
        roster_content,
        semester_5["id"],
    )
    assert initial_preview.status_code == 200, initial_preview.text
    assert initial_preview.json()["new_students"] == 64
    initial_import = upload(
        "/api/students/import",
        target_section["id"],
        roster_content,
        semester_5["id"],
    )
    assert initial_import.status_code == 200, initial_import.text
    assert initial_import.json()["imported_count"] == 64

    original_roster = client.get(
        f"/api/sections/{target_section['id']}/students",
        headers=headers,
    ).json()
    original_ids = {
        student["register_no"]: student["id"]
        for student in original_roster
    }
    assert len(original_ids) == 64

    sibling_student = client.post(
        "/api/students",
        headers=headers,
        json={
            "register_no": f"RST-SIB-{token}",
            "name": "UNRELATED SECTION STUDENT",
            "section_id": sibling_section["id"],
        },
    )
    assert sibling_student.status_code == 201, sibling_student.text

    with SessionLocal() as db:
        target_student_id = original_ids[student_rows[0][0]]
        db.query(Student).filter(Student.id == target_student_id).update(
            {Student.name: "restore student 001"},
            synchronize_session=False,
        )
        subject = db.query(Subject).filter(
            Subject.batch_id == reference_section["batch_id"],
            Subject.department_id == reference_section["department_id"],
            Subject.year_id == year_3["id"],
            Subject.semester_id == semester_5["id"],
        ).first()
        assert subject is not None
        target_exam = Exam(
            name=f"RESTORE TARGET EXAM {token}",
            exam_type="CUSTOM",
            batch_id=reference_section["batch_id"],
            department_id=reference_section["department_id"],
            year_id=year_3["id"],
            semester_id=semester_5["id"],
            section_id=target_section["id"],
            subject_id=subject.id,
            pass_percentage=50,
        )
        sibling_exam = Exam(
            name=f"RESTORE SIBLING EXAM {token}",
            exam_type="CUSTOM",
            batch_id=reference_section["batch_id"],
            department_id=reference_section["department_id"],
            year_id=year_3["id"],
            semester_id=semester_5["id"],
            section_id=sibling_section["id"],
            subject_id=subject.id,
            pass_percentage=50,
        )
        db.add_all([target_exam, sibling_exam])
        db.flush()
        target_exam_id = target_exam.id
        sibling_exam_id = sibling_exam.id
        db.add_all([
            StudentMark(
                exam_id=target_exam_id,
                student_id=target_student_id,
                question_number="Q1",
                obtained_mark=8,
            ),
            StudentMark(
                exam_id=sibling_exam_id,
                student_id=sibling_student.json()["id"],
                question_number="Q1",
                obtained_mark=7,
            ),
        ])
        db.commit()

    first_delete = client.delete(
        f"/api/academic/sections/{target_section['id']}",
        headers=headers,
    )
    assert first_delete.status_code == 200, first_delete.text
    with SessionLocal() as db:
        students = db.query(Student).filter(
            Student.id.in_(original_ids.values())
        ).all()
        assert len(students) == 64
        assert {student.id for student in students} == set(original_ids.values())
        assert all(student.section_id is None for student in students)
        placements = db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id.in_(original_ids.values()),
            StudentAcademicPlacement.is_current.is_(True),
        ).all()
        assert len(placements) == 64
        assert all(placement.section_id is None for placement in placements)
        assert all(placement.section_name == logical_section_name for placement in placements)
        assert db.query(Exam).filter(Exam.id == target_exam_id).count() == 0
        assert db.query(StudentMark).filter(StudentMark.exam_id == target_exam_id).count() == 0
        assert db.query(Exam).filter(Exam.id == sibling_exam_id).count() == 1
        assert db.query(StudentMark).filter(StudentMark.exam_id == sibling_exam_id).count() == 1

    recreated_section = create_section(logical_section_name)
    assert recreated_section["id"] != target_section["id"]
    first_restore_preview = upload(
        "/api/students/import-preview",
        recreated_section["id"],
        roster_content,
        semester_5["id"],
    )
    assert first_restore_preview.status_code == 200, first_restore_preview.text
    first_restore_summary = first_restore_preview.json()
    assert first_restore_summary["total_rows"] == 64
    assert first_restore_summary["new_students"] == 0
    assert first_restore_summary["already_assigned"] == 0
    assert first_restore_summary["eligible_for_restoration"] == 64
    assert first_restore_summary["placement_conflicts"] == 0
    assert first_restore_summary["invalid_rows"] == 0
    first_restore = upload(
        "/api/students/import",
        recreated_section["id"],
        roster_content,
        semester_5["id"],
    )
    assert first_restore.status_code == 200, first_restore.text
    assert first_restore.json()["restored_count"] == 64
    restored_roster = client.get(
        f"/api/sections/{recreated_section['id']}/students",
        headers=headers,
    ).json()
    assert {student["register_no"]: student["id"] for student in restored_roster} == original_ids
    assert next(
        student["name"] for student in restored_roster
        if student["id"] == target_student_id
    ) == "restore student 001"

    with SessionLocal() as db:
        placements_after_restore = db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id.in_(original_ids.values())
        ).count()
        assert placements_after_restore == 128
        assert db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id.in_(original_ids.values()),
            StudentAcademicPlacement.is_current.is_(True),
        ).count() == 64

    repeated_preview = upload(
        "/api/students/import-preview",
        recreated_section["id"],
        roster_content,
        semester_5["id"],
    )
    assert repeated_preview.status_code == 200, repeated_preview.text
    assert repeated_preview.json()["already_assigned"] == 64
    repeated_import = upload(
        "/api/students/import",
        recreated_section["id"],
        roster_content,
        semester_5["id"],
    )
    assert repeated_import.status_code == 200, repeated_import.text
    assert repeated_import.json()["restored_count"] == 0

    second_delete = client.delete(
        f"/api/academic/sections/{recreated_section['id']}",
        headers=headers,
    )
    assert second_delete.status_code == 200, second_delete.text
    second_recreated_section = create_section(logical_section_name)
    with SessionLocal() as db:
        db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id.in_(original_ids.values()),
            StudentAcademicPlacement.is_current.is_(True),
            StudentAcademicPlacement.section_id.is_(None),
        ).update(
            {StudentAcademicPlacement.section_name: None},
            synchronize_session=False,
        )
        db.commit()
    second_restore_preview = upload(
        "/api/students/import-preview",
        second_recreated_section["id"],
        roster_content,
        semester_5["id"],
    )
    assert second_restore_preview.status_code == 200, second_restore_preview.text
    assert second_restore_preview.json()["eligible_for_restoration"] == 64
    assert second_restore_preview.json()["placement_conflicts"] == 0
    assert any(
        "previous Section name was not recorded" in message
        for message in second_restore_preview.json()["errors"]
    )
    second_restore = upload(
        "/api/students/import",
        second_recreated_section["id"],
        roster_content,
        semester_5["id"],
    )
    assert second_restore.status_code == 200, second_restore.text
    assert second_restore.json()["restored_count"] == 64
    final_roster = client.get(
        f"/api/sections/{second_recreated_section['id']}/students",
        headers=headers,
    ).json()
    assert len(final_roster) == 64
    assert {student["register_no"]: student["id"] for student in final_roster} == original_ids

    with SessionLocal() as db:
        assert db.query(Student).filter(
            Student.batch_id == reference_section["batch_id"],
            Student.register_no.like(f"RST{token}-%"),
        ).count() == 64
        assert db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id.in_(original_ids.values()),
            StudentAcademicPlacement.is_current.is_(True),
        ).count() == 64
        assert db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id.in_(original_ids.values())
        ).count() == 192
        assert db.query(Exam).filter(Exam.id == target_exam_id).count() == 0
        assert db.query(Exam).filter(Exam.id == sibling_exam_id).count() == 1
        assert db.query(StudentMark).filter(
            StudentMark.exam_id == sibling_exam_id
        ).count() == 1
        sibling_student_record = db.get(Student, sibling_student.json()["id"])
        db.refresh(sibling_student_record)
        assert sibling_student_record.section_id == sibling_section["id"]


def test_mixed_import_restores_existing_identity_and_creates_only_the_new_student():
    headers = _headers()
    _, year_3, reference_section = _section_context(headers)
    section_name = f"M{uuid4().hex[:8].upper()}"
    register_no = f"MIXED-{uuid4().hex[:8].upper()}"
    new_register_no = f"MIXED-NEW-{uuid4().hex[:8].upper()}"

    def create_section():
        response = client.post(
            "/api/academic/sections",
            headers=headers,
            json={
                "name": section_name,
                "batch_id": reference_section["batch_id"],
                "department_id": reference_section["department_id"],
                "year_id": year_3["id"],
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    original_section = create_section()
    original_student = client.post(
        "/api/students",
        headers=headers,
        json={
            "register_no": register_no,
            "name": "ORIGINAL STUDENT NAME",
            "section_id": original_section["id"],
        },
    )
    assert original_student.status_code == 201, original_student.text
    student_id = original_student.json()["id"]
    assert client.delete(
        f"/api/academic/sections/{original_section['id']}",
        headers=headers,
    ).status_code == 200
    destination = create_section()

    content = (
        "Register Number,Student Name\n"
        f"{register_no},original-student name\n"
        f"{new_register_no},NEW STUDENT\n"
    )
    preview = client.post(
        "/api/students/import-preview",
        files={"file": ("mixed.csv", content, "text/csv")},
        data={"section_id": str(destination["id"])},
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["new_students"] == 1
    assert preview.json()["eligible_for_restoration"] == 1
    assert preview.json()["placement_conflicts"] == 0
    assert preview.json()["invalid_rows"] == 0

    imported = client.post(
        "/api/students/import",
        files={"file": ("mixed.csv", content, "text/csv")},
        data={"section_id": str(destination["id"]), "confirm": "true"},
        headers=headers,
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported_count"] == 1
    assert imported.json()["restored_count"] == 1

    roster = client.get(
        f"/api/sections/{destination['id']}/students",
        headers=headers,
    ).json()
    existing = next(student for student in roster if student["register_no"] == register_no)
    assert existing["id"] == student_id
    assert existing["name"] == "ORIGINAL STUDENT NAME"
    assert any(student["register_no"] == new_register_no for student in roster)
    with SessionLocal() as db:
        assert db.query(Student).filter(
            Student.batch_id == reference_section["batch_id"],
            Student.register_no == register_no,
        ).count() == 1
        assert db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id == student_id,
            StudentAcademicPlacement.is_current.is_(True),
            StudentAcademicPlacement.section_id == destination["id"],
        ).count() == 1


def test_detached_student_with_incompatible_academic_context_is_a_conflict():
    headers = _headers()
    _, year_3, reference_section = _section_context(headers)
    year_4 = next(
        year for year in client.get("/api/academic/years", headers=headers).json()
        if year["year_number"] == 4
    )
    section_name = f"X{uuid4().hex[:7].upper()}"
    register_no = f"CONTEXT-{uuid4().hex[:8].upper()}"
    source = client.post(
        "/api/academic/sections",
        headers=headers,
        json={
            "name": section_name,
            "batch_id": reference_section["batch_id"],
            "department_id": reference_section["department_id"],
            "year_id": year_3["id"],
        },
    )
    assert source.status_code == 201, source.text
    student = client.post(
        "/api/students",
        headers=headers,
        json={
            "register_no": register_no,
            "name": "CONTEXT STUDENT",
            "section_id": source.json()["id"],
        },
    )
    assert student.status_code == 201, student.text
    deleted = client.delete(
        f"/api/academic/sections/{source.json()['id']}",
        headers=headers,
    )
    assert deleted.status_code == 200, deleted.text

    incompatible_destination = client.post(
        "/api/academic/sections",
        headers=headers,
        json={
            "name": section_name,
            "batch_id": reference_section["batch_id"],
            "department_id": reference_section["department_id"],
            "year_id": year_4["id"],
        },
    )
    assert incompatible_destination.status_code == 201, incompatible_destination.text
    preview = client.post(
        "/api/students/import-preview",
        files={
            "file": (
                "incompatible.csv",
                f"Register Number,Student Name\n{register_no},CONTEXT STUDENT\n",
                "text/csv",
            )
        },
        data={"section_id": str(incompatible_destination.json()["id"])},
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["placement_conflicts"] == 1
    assert preview.json()["invalid_rows"] == 0
    assert any("incompatible prior academic context" in message for message in preview.json()["errors"])

    student_detail = client.get(
        f"/api/students/{student.json()['id']}",
        headers=headers,
    )
    assert student_detail.status_code == 200, student_detail.text
    assert student_detail.json()["section_id"] is None
    assert student_detail.json()["placement_history"][-1]["section_name"] == section_name


def test_import_rollback_when_invalid_rows_present():
    headers = _headers()
    _, _, section_a = _section_context(headers)
    content = "Register Number,Student Name\nTEST-REG-0020,VALID ONE\n,INVALID NAME\n"
    before = client.get(f"/api/sections/{section_a['id']}/students", headers=headers).json()
    resp = client.post(
        "/api/students/import",
        files={"file": ("rollback.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"]), "confirm": "true"},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    after = client.get(f"/api/sections/{section_a['id']}/students", headers=headers).json()
    assert len(after) == len(before)


def test_empty_student_import_is_rejected_without_changing_the_roster():
    headers = _headers()
    _, _, section_a = _section_context(headers)
    before = client.get(f"/api/sections/{section_a['id']}/students", headers=headers).json()
    response = client.post(
        "/api/students/import",
        files={"file": ("empty.csv", "Register Number,Student Name\n", "text/csv")},
        data={"section_id": str(section_a["id"]), "confirm": "true"},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "The uploaded roster contains no student rows."
    after = client.get(f"/api/sections/{section_a['id']}/students", headers=headers).json()
    assert len(after) == len(before)


def test_import_requires_selected_section_context_and_has_no_semester_field_requirement():
    headers = _headers()
    depts = client.get("/api/departments", headers=headers).json()
    cse = next(d for d in depts if d["code"] == "CSE")
    years = client.get("/api/academic/years", headers=headers).json()
    year_3 = next(y for y in years if y["year_number"] == 3)
    sections = client.get(f"/api/academic/sections?department_id={cse['id']}&year_id={year_3['id']}", headers=headers).json()
    section_b = next(s for s in sections if s["name"] == "B")
    content = "Register Number,Student Name\nTEST-REG-0021,SECTION B STUDENT\n"
    resp = client.post(
        "/api/students/import-preview",
        files={"file": ("section_b.csv", content, "text/csv")},
        data={"section_id": str(section_b["id"])},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["valid_rows"] == 1

    import_resp = client.post(
        "/api/students/import",
        files={"file": ("section_b.csv", content, "text/csv")},
        data={"section_id": str(section_b["id"]), "confirm": "true"},
        headers=headers,
    )
    assert import_resp.status_code == 200, import_resp.text
    roster = client.get(f"/api/sections/{section_b['id']}/students", headers=headers).json()
    assert any(student["register_no"] == "TEST-REG-0021" for student in roster)


def test_student_edit_updates_fields_and_rejects_duplicates_or_empty_values():
    headers = _headers()
    _, _, section_a = _section_context(headers)
    roster = client.get(f"/api/sections/{section_a['id']}/students", headers=headers).json()
    target = next(student for student in roster if student["register_no"] == "TEST-REG-0001")
    other = next(student for student in roster if student["id"] != target["id"])

    unchanged_register = client.put(
        f"/api/students/{target['id']}",
        json={"register_no": target["register_no"], "name": "  EDITED NAME  "},
        headers=headers,
    )
    assert unchanged_register.status_code == 200, unchanged_register.text
    assert unchanged_register.json()["register_no"] == target["register_no"]
    assert unchanged_register.json()["name"] == "EDITED NAME"

    changed_register = client.put(
        f"/api/students/{target['id']}",
        json={"register_no": " EDIT-REG-TEST-REG-0001 ", "name": " UPDATED STUDENT "},
        headers=headers,
    )
    assert changed_register.status_code == 200, changed_register.text
    assert changed_register.json()["register_no"] == "EDIT-REG-TEST-REG-0001"
    assert isinstance(changed_register.json()["register_no"], str)
    assert changed_register.json()["name"] == "UPDATED STUDENT"
    assert changed_register.json()["section_id"] == section_a["id"]

    duplicate = client.put(
        f"/api/students/{target['id']}",
        json={"register_no": other["register_no"], "name": "DUPLICATE"},
        headers=headers,
    )
    assert duplicate.status_code == 400

    empty_register = client.put(
        f"/api/students/{target['id']}",
        json={"register_no": "", "name": "VALID NAME"},
        headers=headers,
    )
    assert empty_register.status_code == 422
    empty_name = client.put(
        f"/api/students/{target['id']}",
        json={"register_no": "VALID123", "name": ""},
        headers=headers,
    )
    assert empty_name.status_code == 422
    whitespace_only = client.put(
        f"/api/students/{target['id']}",
        json={"register_no": "   ", "name": "   "},
        headers=headers,
    )
    assert whitespace_only.status_code == 400

    current = client.get(f"/api/students/{target['id']}", headers=headers).json()
    assert current["register_no"] == "EDIT-REG-TEST-REG-0001"
    assert current["name"] == "UPDATED STUDENT"


def test_student_delete_archives_and_restore_returns_student_to_active_roster():
    headers = _headers()
    _, _, section_a = _section_context(headers)
    created = client.post(
        "/api/students",
        json={"register_no": "DELETE-SAFE-1", "name": "SAFE DELETE", "section_id": section_a["id"]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    student_id = created.json()["id"]

    deleted = client.delete(f"/api/students/{student_id}", headers=headers)
    assert deleted.status_code == 204, deleted.text
    roster = client.get(f"/api/sections/{section_a['id']}/students", headers=headers).json()
    assert all(student["id"] != student_id for student in roster)

    archived_roster = client.get(
        f"/api/sections/{section_a['id']}/students?include_archived=true",
        headers=headers,
    ).json()
    archived_student = next(student for student in archived_roster if student["id"] == student_id)
    assert archived_student["archived_at"] is not None

    restored = client.post(f"/api/students/{student_id}/restore", headers=headers)
    assert restored.status_code == 200, restored.text
    assert restored.json()["archived_at"] is None
    active_roster = client.get(f"/api/sections/{section_a['id']}/students", headers=headers).json()
    assert any(student["id"] == student_id for student in active_roster)


def test_student_with_marks_can_be_archived_and_restored_without_changing_history():
    headers = _headers()
    cse, year_3, section_a = _section_context(headers)
    semesters = client.get(f"/api/academic/semesters?year_id={year_3['id']}", headers=headers).json()
    semester_5 = next(semester for semester in semesters if semester["semester_number"] == 5)
    student_response = client.post(
        "/api/students",
        json={"register_no": "DELETE-UNSAFE-1", "name": "UNSAFE DELETE", "section_id": section_a["id"]},
        headers=headers,
    )
    assert student_response.status_code == 201, student_response.text
    student_id = student_response.json()["id"]

    with SessionLocal() as db:
        subject = db.query(Subject).filter(
            Subject.department_id == cse["id"],
            Subject.year_id == year_3["id"],
            Subject.semester_id == semester_5["id"],
        ).first()
        exam = Exam(
            name="Unsafe Student Delete Test",
            exam_type="CUSTOM",
            batch_id=section_a["batch_id"],
            department_id=cse["id"],
            year_id=year_3["id"],
            semester_id=semester_5["id"],
            section_id=section_a["id"],
            subject_id=subject.id,
            pass_percentage=50,
        )
        db.add(exam)
        db.flush()
        exam_id = exam.id
        db.add(StudentMark(
            exam_id=exam_id,
            student_id=student_id,
            question_number="Q1",
            obtained_mark=7,
        ))
        db.commit()

    archived = client.delete(f"/api/students/{student_id}", headers=headers)
    assert archived.status_code == 204, archived.text
    active_roster = client.get(f"/api/sections/{section_a['id']}/students", headers=headers).json()
    assert all(student["id"] != student_id for student in active_roster)
    archived_roster = client.get(
        f"/api/sections/{section_a['id']}/students?include_archived=true",
        headers=headers,
    ).json()
    assert any(student["id"] == student_id and student["archived_at"] for student in archived_roster)

    with SessionLocal() as db:
        assert db.query(Student).filter(Student.id == student_id).one_or_none() is not None
        assert db.query(Exam).filter(Exam.id == exam_id).one_or_none() is not None
        assert db.query(StudentMark).filter(
            StudentMark.exam_id == exam_id,
            StudentMark.student_id == student_id,
        ).count() == 1

    restored = client.post(f"/api/students/{student_id}/restore", headers=headers)
    assert restored.status_code == 200, restored.text
    restored_roster = client.get(f"/api/sections/{section_a['id']}/students", headers=headers).json()
    assert any(student["id"] == student_id for student in restored_roster)

    with SessionLocal() as db:
        assert db.query(Exam).filter(Exam.id == exam_id).one_or_none() is not None
        assert db.query(StudentMark).filter(
            StudentMark.exam_id == exam_id,
            StudentMark.student_id == student_id,
        ).count() == 1


def test_archived_register_conflicts_until_existing_student_is_restored():
    headers = _headers()
    _, _, section_a = _section_context(headers)
    register_no = "ARCHIVE-REUSE-1"
    original = client.post(
        "/api/students",
        json={"register_no": register_no, "name": "ORIGINAL STUDENT", "section_id": section_a["id"]},
        headers=headers,
    )
    assert original.status_code == 201, original.text
    original_id = original.json()["id"]
    assert client.delete(f"/api/students/{original_id}", headers=headers).status_code == 204

    duplicate = client.post(
        "/api/students",
        json={"register_no": register_no, "name": "ORIGINAL STUDENT", "section_id": section_a["id"]},
        headers=headers,
    )
    assert duplicate.status_code == 409
    assert "already exists in this Batch" in duplicate.json()["detail"]

    restored = client.post(f"/api/students/{original_id}/restore", headers=headers)
    assert restored.status_code == 200, restored.text
    assert restored.json()["id"] == original_id
    assert restored.json()["archived_at"] is None

    with SessionLocal() as db:
        assert db.query(Student).filter(Student.batch_id == original.json()["batch_id"], Student.register_no == register_no).count() == 1


def test_register_numbers_identify_one_student_across_a_batch():
    headers = _headers()
    _, _, section_a = _section_context(headers)
    sections = client.get(
        f"/api/academic/sections?department_id={section_a['department_id']}&year_id={section_a['year_id']}",
        headers=headers,
    ).json()
    section_b = next(section for section in sections if section["id"] != section_a["id"])
    register_no = "SECTION-SCOPED-REGISTER"

    created_a = client.post(
        "/api/students",
        json={"register_no": register_no, "name": "SECTION A STUDENT", "section_id": section_a["id"]},
        headers=headers,
    )
    assert created_a.status_code == 201, created_a.text

    created_b = client.post(
        "/api/students",
        json={"register_no": register_no, "name": "SECTION A STUDENT", "section_id": section_b["id"]},
        headers=headers,
    )
    assert created_b.status_code == 409, created_b.text
    assert "Select the existing student" in created_b.json()["detail"]

    moved = client.put(
        f"/api/students/{created_a.json()['id']}/placement",
        json={"section_id": section_b["id"]},
        headers=headers,
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["section_id"] == section_b["id"]
    assert moved.json()["id"] == created_a.json()["id"]

    duplicate = client.post(
        "/api/students",
        json={"register_no": register_no, "name": "DUPLICATE IN SECTION A", "section_id": section_a["id"]},
        headers=headers,
    )
    assert duplicate.status_code == 409


def test_section_roster_uses_natural_register_number_order():
    headers = _headers()
    _, _, section_a = _section_context(headers)
    register_numbers = ["SORT-NATURAL-1", "SORT-NATURAL-2", "SORT-NATURAL-10"]
    created_ids = []

    for register_no in register_numbers:
        response = client.post(
            "/api/students",
            json={"register_no": register_no, "name": "SORT ORDER STUDENT", "section_id": section_a["id"]},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        created_ids.append(response.json()["id"])

    roster = client.get(f"/api/sections/{section_a['id']}/students", headers=headers).json()
    positions = {student["register_no"]: index for index, student in enumerate(roster)}
    assert positions[register_numbers[0]] < positions[register_numbers[1]] < positions[register_numbers[2]]

    for student_id in created_ids:
        assert client.delete(f"/api/students/{student_id}", headers=headers).status_code == 204


def test_archived_remove_all_deletes_only_archived_students_and_marks_atomically():
    headers = _headers()
    cse, year_3, section_a = _section_context(headers)
    semesters = client.get(f"/api/academic/semesters?year_id={year_3['id']}", headers=headers).json()
    semester_5 = next(semester for semester in semesters if semester["semester_number"] == 5)

    with SessionLocal() as db:
        test_section = Section(
            name="PERM-TEST",
            batch_id=section_a["batch_id"],
            department_id=cse["id"],
            year_id=year_3["id"],
        )
        db.add(test_section)
        db.flush()
        test_section_id = test_section.id
        subject = db.query(Subject).filter(
            Subject.department_id == cse["id"],
            Subject.year_id == year_3["id"],
            Subject.semester_id == semester_5["id"],
        ).first()
        exam = Exam(
            name="Archived Permanent Delete Test",
            exam_type="CUSTOM",
            batch_id=test_section.batch_id,
            department_id=cse["id"],
            year_id=year_3["id"],
            semester_id=semester_5["id"],
            section_id=test_section_id,
            subject_id=subject.id,
            pass_percentage=50,
        )
        db.add(exam)
        db.commit()
        exam_id = exam.id

    test_students = []
    for register_no, name in (
        ("PERM-DELETE-1", "PERMANENT DELETE ONE"),
        ("PERM-DELETE-2", "PERMANENT DELETE TWO"),
        ("PERM-KEEP-1", "UNRELATED ACTIVE STUDENT"),
    ):
        response = client.post(
            "/api/students",
            json={"register_no": register_no, "name": name, "section_id": test_section_id},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        test_students.append(response.json())

    first_id, second_id, unrelated_id = [student["id"] for student in test_students]
    with SessionLocal() as db:
        for student_id in (first_id, second_id, unrelated_id):
            db.add(StudentMark(
                exam_id=exam_id,
                student_id=student_id,
                question_number="Q1",
                obtained_mark=7,
            ))
        db.commit()

    for student_id in (first_id, second_id):
        archived = client.delete(f"/api/students/{student_id}", headers=headers)
        assert archived.status_code == 204, archived.text

    archived_roster = client.get(
        f"/api/sections/{test_section_id}/students?include_archived=true",
        headers=headers,
    ).json()
    assert {student["id"] for student in archived_roster if student["archived_at"]} == {first_id, second_id}

    restored = client.post(f"/api/students/{second_id}/restore", headers=headers)
    assert restored.status_code == 200, restored.text
    active_roster = client.get(f"/api/sections/{test_section_id}/students", headers=headers).json()
    assert {student["id"] for student in active_roster} == {second_id, unrelated_id}
    rearchived = client.delete(f"/api/students/{second_id}", headers=headers)
    assert rearchived.status_code == 204, rearchived.text

    trigger_name = "fail_permanent_student_delete_test"
    with SessionLocal() as db:
        db.execute(text(
            f"CREATE TRIGGER {trigger_name} BEFORE DELETE ON students "
            f"WHEN OLD.id IN ({first_id}, {second_id}) "
            "BEGIN SELECT RAISE(ABORT, 'forced test failure'); END"
        ))
        db.commit()
        try:
            with pytest.raises(IntegrityError):
                StudentService(db).permanently_delete_archived_students(test_section_id)
            assert db.query(Student).filter(Student.id.in_([first_id, second_id])).count() == 2
            assert db.query(StudentMark).filter(
                StudentMark.student_id.in_([first_id, second_id])
            ).count() == 2
        finally:
            db.execute(text(f"DROP TRIGGER IF EXISTS {trigger_name}"))
            db.commit()

    permanently_deleted = client.delete(
        f"/api/sections/{test_section_id}/students/archived",
        headers=headers,
    )
    assert permanently_deleted.status_code == 200, permanently_deleted.text
    assert permanently_deleted.json()["deleted_count"] == 2
    final_roster = client.get(
        f"/api/sections/{test_section_id}/students?include_archived=true",
        headers=headers,
    ).json()
    assert {student["id"] for student in final_roster} == {unrelated_id}

    with SessionLocal() as db:
        assert db.query(Student).filter(Student.id.in_([first_id, second_id])).count() == 0
        assert db.query(StudentMark).filter(
            StudentMark.student_id.in_([first_id, second_id])
        ).count() == 0
        assert db.query(Student).filter(Student.id == unrelated_id).one_or_none() is not None
        assert db.query(StudentMark).filter(StudentMark.student_id == unrelated_id).count() == 1
        assert db.query(Exam).filter(Exam.id == exam_id).one_or_none() is not None


def test_individual_archived_delete_removes_only_selected_student_and_marks():
    headers = _headers()
    cse, year_3, section_a = _section_context(headers)
    semesters = client.get(f"/api/academic/semesters?year_id={year_3['id']}", headers=headers).json()
    semester_5 = next(semester for semester in semesters if semester["semester_number"] == 5)

    with SessionLocal() as db:
        test_section = Section(
            name="INDIV-TEST",
            batch_id=section_a["batch_id"],
            department_id=cse["id"],
            year_id=year_3["id"],
        )
        db.add(test_section)
        db.flush()
        test_section_id = test_section.id
        subject = db.query(Subject).filter(
            Subject.department_id == cse["id"],
            Subject.year_id == year_3["id"],
            Subject.semester_id == semester_5["id"],
        ).first()
        exam = Exam(
            name="Individual Archived Delete Test",
            exam_type="CUSTOM",
            batch_id=test_section.batch_id,
            department_id=cse["id"],
            year_id=year_3["id"],
            semester_id=semester_5["id"],
            section_id=test_section_id,
            subject_id=subject.id,
            pass_percentage=50,
        )
        db.add(exam)
        db.commit()
        exam_id = exam.id

    student_ids = []
    for register_no, name in (
        ("INDIV-DELETE-1", "SELECTED ARCHIVED STUDENT"),
        ("INDIV-KEEP-1", "UNRELATED ACTIVE STUDENT"),
    ):
        created = client.post(
            "/api/students",
            json={"register_no": register_no, "name": name, "section_id": test_section_id},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        student_ids.append(created.json()["id"])

    selected_id, unrelated_id = student_ids
    with SessionLocal() as db:
        for student_id in student_ids:
            db.add(StudentMark(
                exam_id=exam_id,
                student_id=student_id,
                question_number="Q1",
                obtained_mark=6,
            ))
        db.commit()

    archived = client.delete(f"/api/students/{selected_id}", headers=headers)
    assert archived.status_code == 204, archived.text
    archived_roster = client.get(
        f"/api/sections/{test_section_id}/students?include_archived=true",
        headers=headers,
    ).json()
    assert any(student["id"] == selected_id and student["archived_at"] for student in archived_roster)

    deleted = client.delete(f"/api/students/{selected_id}/permanent", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_count"] == 1
    archived_roster = client.get(
        f"/api/sections/{test_section_id}/students?include_archived=true",
        headers=headers,
    ).json()
    assert all(student["id"] != selected_id for student in archived_roster)

    with SessionLocal() as db:
        assert db.query(Student).filter(Student.id == selected_id).one_or_none() is None
        assert db.query(StudentMark).filter(StudentMark.student_id == selected_id).count() == 0
        assert db.query(Student).filter(Student.id == unrelated_id).one_or_none() is not None
        assert db.query(StudentMark).filter(StudentMark.student_id == unrelated_id).count() == 1
        assert db.query(Exam).filter(Exam.id == exam_id).one_or_none() is not None


def test_duplicate_registers_resolve_by_normalized_name_and_restore_only_selected_id():
    headers = _headers()
    _, year_3, section_a = _section_context(headers)
    sections = client.get(
        f"/api/academic/sections?batch_id={section_a['batch_id']}",
        headers=headers,
    ).json()
    section_b = next(section for section in sections if section["name"] == "B")

    def create_identity(register_no, name, section_id, archived=False):
        with SessionLocal() as db:
            student = Student(
                register_no=register_no,
                name=name,
                batch_id=section_a["batch_id"],
                section_id=section_id,
                archived_at=datetime.now(timezone.utc) if archived else None,
            )
            db.add(student)
            db.flush()
            db.add(StudentAcademicPlacement(
                student_id=student.id,
                batch_id=section_a["batch_id"],
                department_id=section_a["department_id"],
                year_id=year_3["id"],
                section_id=section_id,
                section_name="B" if section_id == section_b["id"] else None,
                is_current=True,
            ))
            student_id = student.id
            db.commit()
            return student_id

    excluded_0349 = create_identity("TEST-REG-0349", "Sample Student 1", section_b["id"], archived=True)
    intended_0349 = create_identity("TEST-REG-0349", "Sample Student 2", None)
    intended_0364 = create_identity("TEST-REG-0364", "Sample Student 3", None)
    excluded_0364 = create_identity(
        "TEST-REG-0364",
        "Sample Student 4",
        section_b["id"],
    )
    filler_rows = [
        (f"RESOLVED-{uuid4().hex[:8].upper()}-{number:02d}", f"RESTORATION STUDENT {number:02d}")
        for number in range(1, 63)
    ]
    with SessionLocal() as db:
        for register_no, name in filler_rows:
            student = Student(
                register_no=register_no,
                name=name,
                batch_id=section_a["batch_id"],
                section_id=None,
            )
            db.add(student)
            db.flush()
            db.add(StudentAcademicPlacement(
                student_id=student.id,
                batch_id=section_a["batch_id"],
                department_id=section_a["department_id"],
                year_id=year_3["id"],
                section_id=None,
                section_name=None,
                is_current=True,
            ))
        db.commit()

    roster_rows = list(filler_rows)
    roster_rows.insert(48, ("TEST-REG-0349", "Sample Student 2"))
    roster_rows.append(("TEST-REG-0364", "Sample Student 3"))
    content = "Register Number,Student Name\n" + "".join(
        f"{register_no},{name}\n" for register_no, name in roster_rows
    )

    preview = client.post(
        "/api/students/import-preview",
        files={"file": ("identified_students.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"])},
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    result = preview.json()
    assert result["total_rows"] == 64
    assert result["eligible_for_restoration"] == 64
    assert result["placement_conflicts"] == 0
    assert result["invalid_rows"] == 0
    resolutions = {
        item["register_no"]: item for item in result["identity_resolutions"]
    }
    assert resolutions["TEST-REG-0349"]["selected_student_id"] == intended_0349
    assert resolutions["TEST-REG-0349"]["row_number"] == 49
    assert resolutions["TEST-REG-0349"]["other_student_ids"] == [excluded_0349]
    assert resolutions["TEST-REG-0364"]["selected_student_id"] == intended_0364
    assert resolutions["TEST-REG-0364"]["row_number"] == 64
    assert resolutions["TEST-REG-0364"]["other_student_ids"] == [excluded_0364]
    assert all(
        item["destination_section_id"] == section_a["id"]
        for item in result["identity_resolutions"]
    )

    imported = client.post(
        "/api/students/import",
        files={"file": ("identified_students.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"]), "confirm": "true"},
        headers=headers,
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["restored_count"] == 64

    repeated_preview = client.post(
        "/api/students/import-preview",
        files={"file": ("identified_students.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"])},
        headers=headers,
    )
    assert repeated_preview.status_code == 200, repeated_preview.text
    assert repeated_preview.json()["already_assigned"] == 64
    repeated_import = client.post(
        "/api/students/import",
        files={"file": ("identified_students.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"]), "confirm": "true"},
        headers=headers,
    )
    assert repeated_import.status_code == 200, repeated_import.text
    assert repeated_import.json()["restored_count"] == 0
    assert repeated_import.json()["already_assigned_count"] == 64

    with SessionLocal() as db:
        assert db.query(Student).filter(
            Student.register_no.in_(["TEST-REG-0349", "TEST-REG-0364"]),
            Student.batch_id == section_a["batch_id"],
        ).count() == 4
        assert db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id.in_([intended_0349, intended_0364]),
            StudentAcademicPlacement.section_id == section_a["id"],
            StudentAcademicPlacement.is_current.is_(True),
        ).count() == 2
        assert db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id.in_([excluded_0349, excluded_0364]),
            StudentAcademicPlacement.section_id == section_b["id"],
            StudentAcademicPlacement.is_current.is_(True),
        ).count() == 2
        archived_excluded = db.query(Student).filter(Student.id == excluded_0349).one()
        assert archived_excluded.archived_at is not None
        assert db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id == intended_0349
        ).count() == 2
        assert db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id == intended_0364
        ).count() == 2


def test_duplicate_register_does_not_select_an_identity_when_names_do_not_match():
    headers = _headers()
    _, year_3, section_a = _section_context(headers)
    register_no = f"NO-NAME-{uuid4().hex[:8].upper()}"
    with SessionLocal() as db:
        db.add_all([
            Student(register_no=register_no, name="EXISTING NAME ONE", batch_id=section_a["batch_id"]),
            Student(register_no=register_no, name="EXISTING NAME TWO", batch_id=section_a["batch_id"]),
        ])
        db.commit()
    content = f"Register Number,Student Name\n{register_no},UNRELATED UPLOADED NAME\n"
    preview = client.post(
        "/api/students/import-preview",
        files={"file": ("unmatched_identity.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"])},
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    result = preview.json()
    assert result["new_students"] == 0
    assert result["placement_conflicts"] == 1
    assert result["identity_resolutions"][0]["selected_student_id"] is None
    assert result["identity_resolutions"][0]["resolution_status"] == "unresolved"
    assert len(result["identity_resolutions"][0]["candidate_student_ids"]) == 2
    assert "no existing student name matches" in " ".join(result["errors"])


def test_duplicate_register_with_multiple_matching_names_remains_unresolved():
    headers = _headers()
    _, _, section_a = _section_context(headers)
    register_no = f"AMBIGUOUS-NAME-{uuid4().hex[:8].upper()}"
    with SessionLocal() as db:
        db.add_all([
            Student(register_no=register_no, name="SAME STUDENT NAME", batch_id=section_a["batch_id"]),
            Student(register_no=register_no, name="same-student name", batch_id=section_a["batch_id"]),
        ])
        db.commit()

    content = f"Register Number,Student Name\n{register_no},Same Student Name\n"
    preview = client.post(
        "/api/students/import-preview",
        files={"file": ("ambiguous_identity.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"])},
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    result = preview.json()
    assert result["placement_conflicts"] == 1
    assert result["identity_resolutions"][0]["selected_student_id"] is None
    assert len(result["identity_resolutions"][0]["candidate_student_ids"]) == 2
    assert "match multiple existing student identities" in " ".join(result["errors"])


def test_name_matching_another_section_identity_remains_a_placement_conflict():
    headers = _headers()
    _, year_3, section_a = _section_context(headers)
    sections = client.get(
        f"/api/academic/sections?batch_id={section_a['batch_id']}",
        headers=headers,
    ).json()
    section_b = next(section for section in sections if section["name"] == "B")

    with SessionLocal() as db:
        detached = Student(
            register_no="IDENTITY-SECTION-CONFLICT",
            name="INTENDED DETACHED STUDENT",
            batch_id=section_a["batch_id"],
            section_id=None,
        )
        assigned = Student(
            register_no="IDENTITY-SECTION-CONFLICT",
            name="SECTION B STUDENT",
            batch_id=section_a["batch_id"],
            section_id=section_b["id"],
        )
        db.add_all([detached, assigned])
        db.flush()
        detached_id = detached.id
        assigned_id = assigned.id
        db.add_all([
            StudentAcademicPlacement(
                student_id=detached_id,
                batch_id=section_a["batch_id"],
                department_id=section_a["department_id"],
                year_id=year_3["id"],
                section_id=None,
                section_name=None,
                is_current=True,
            ),
            StudentAcademicPlacement(
                student_id=assigned_id,
                batch_id=section_a["batch_id"],
                department_id=section_a["department_id"],
                year_id=year_3["id"],
                section_id=section_b["id"],
                section_name="B",
                is_current=True,
            ),
        ])
        db.commit()

    content = "Register Number,Student Name\nIDENTITY-SECTION-CONFLICT,SECTION B STUDENT\n"
    preview = client.post(
        "/api/students/import-preview",
        files={"file": ("section_b_identity.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"])},
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    result = preview.json()
    assert result["placement_conflicts"] == 1
    assert result["eligible_for_restoration"] == 0
    resolution = result["identity_resolutions"][0]
    assert resolution["selected_student_id"] == assigned_id
    assert resolution["other_student_ids"] == [detached_id]
    assert resolution["destination_section_id"] == section_a["id"]
    assert resolution["resolution_status"] == "conflict"

    attempted_import = client.post(
        "/api/students/import",
        files={"file": ("section_b_identity.csv", content, "text/csv")},
        data={"section_id": str(section_a["id"]), "confirm": "true"},
        headers=headers,
    )
    assert attempted_import.status_code == 200, attempted_import.text
    assert attempted_import.json()["restored_count"] == 0
    assert attempted_import.json()["skipped_conflict_count"] == 1
    with SessionLocal() as db:
        assert db.query(Student).filter(Student.id == assigned_id).one().section_id == section_b["id"]
        assert db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id == assigned_id,
            StudentAcademicPlacement.is_current.is_(True),
        ).one().section_id == section_b["id"]
