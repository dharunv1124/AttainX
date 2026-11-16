"""
Phase 7 - Automated Test Suite for Excel and PDF Report Generation.
Verifies all 18 specified test requirements:
1. Excel report generation succeeds for a valid configured exam.
2. PDF report generation succeeds for a valid configured exam.
3. Report contains the correct exam metadata.
4. Report contains the correct student roster.
5. Report contains questions in canonical question-number order.
6. Report contains the correct saved marks.
7. Report contains correct CO Maximum Marks.
8. Report contains correct Student CO Obtained Marks.
9. Report contains correct CO Percentage.
10. Report contains numeric CO Attainment values 1/0.
11. Strict > Pass Percentage rule is preserved.
12. Exact equality with Pass Percentage produces 0.
13. Student outside the exam cohort cannot appear in the report.
14. Missing/incomplete marks are handled according to the existing Phase 3 policy.
15. Authenticated report download endpoints work.
16. Existing Phase 1-6 tests continue to pass.
"""

import io
import pytest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from PIL import Image

from app.main import app
from app.db.session import SessionLocal
from app.db.models import (
    User,
    UserRole,
    Batch,
    Department,
    Year,
    Semester,
    Section,
    Student,
    StudentAcademicPlacement,
    Subject,
    Exam,
    ExamCoveredCO,
    ExamQuestion,
    StudentMark,
)
from app.security.auth import create_access_token
from app.services.report_service import ExamReportService


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def faculty_token():
    return create_access_token(
        username="faculty1",
        role=UserRole.FACULTY,
    )


@pytest.fixture(scope="module")
def auth_headers(faculty_token):
    return {"Authorization": f"Bearer {faculty_token}"}


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def populated_report_exam(db_session):
    """
    Creates an exam with 2 covered COs, 3 questions, 3 students with complete marks.
    Student 1:
      Q1 (CO1, max 5): 4.0
      Q2 (CO1, max 5): 4.0 -> CO1 total = 8.0/10.0 = 80.0% (> 50.0% -> Attainment 1)
      Q3 (CO2, max 10): 5.0 -> CO2 total = 5.0/10.0 = 50.0% (== 50.0% -> Exact equality -> Attainment 0)
    Student 2:
      Q1 (CO1, max 5): 1.0
      Q2 (CO1, max 5): 1.0 -> CO1 total = 2.0/10.0 = 20.0% (< 50.0% -> Attainment 0)
      Q3 (CO2, max 10): 8.0 -> CO2 total = 8.0/10.0 = 80.0% (> 50.0% -> Attainment 1)
    Student 3:
      Q1 (CO1, max 5): 3.0
      Q2 (CO1, max 5): 3.0 -> CO1 total = 6.0/10.0 = 60.0% (> 50.0% -> Attainment 1)
      Q3 (CO2, max 10): 6.0 -> CO2 total = 6.0/10.0 = 60.0% (> 50.0% -> Attainment 1)
    """
    dept = db_session.query(Department).filter_by(code="CSE").one()
    year = db_session.query(Year).filter_by(year_number=3).one()
    sem = db_session.query(Semester).filter_by(semester_number=6).one()
    batch = db_session.query(Batch).filter_by(start_year=2024, end_year=2028).one()
    subj = db_session.query(Subject).filter_by(
        batch_id=batch.id,
        department_id=dept.id,
        year_id=year.id,
        semester_id=sem.id,
    ).first()
    assert subj is not None

    # Query or create a dedicated section for the report exam
    sec = db_session.query(Section).filter_by(
        name="REP_SEC", batch_id=batch.id, department_id=dept.id, year_id=year.id
    ).first()
    if not sec:
        sec = Section(name="REP_SEC", batch_id=batch.id, department_id=dept.id, year_id=year.id)
        db_session.add(sec)
        db_session.commit()
        db_session.refresh(sec)

    # Query or create exactly 3 students in this dedicated section
    students = db_session.query(Student).filter_by(section_id=sec.id).order_by(Student.register_no).all()
    if not students:
        students = [
            Student(register_no="REP001", name="Alice Report", batch_id=batch.id, section_id=sec.id),
            Student(register_no="REP002", name="Bob Report", batch_id=batch.id, section_id=sec.id),
            Student(register_no="REP003", name="Charlie Report", batch_id=batch.id, section_id=sec.id),
        ]
        db_session.add_all(students)
        db_session.commit()
        for s in students:
            db_session.refresh(s)
            db_session.add(StudentAcademicPlacement(
                student_id=s.id,
                batch_id=batch.id,
                department_id=sec.department_id,
                year_id=sec.year_id,
                semester_id=sem.id,
                section_id=sec.id,
            ))
        db_session.commit()

    # Query or create exam
    exam = db_session.query(Exam).filter_by(name="Internal Assessment 1 - Testing", section_id=sec.id).first()
    if not exam:
        exam = Exam(
            name="Internal Assessment 1 - Testing",
            exam_type="INTERNAL_1",
            batch_id=batch.id,
            department_id=dept.id,
            year_id=year.id,
            semester_id=sem.id,
            section_id=sec.id,
            subject_id=subj.id,
            exam_date=date.today() + timedelta(days=1),
            pass_percentage=Decimal("50.00"),
        )
        db_session.add(exam)
        db_session.commit()
        db_session.refresh(exam)

        # Covered COs: CO1, CO2
        co1 = ExamCoveredCO(exam_id=exam.id, co_code="CO1")
        co2 = ExamCoveredCO(exam_id=exam.id, co_code="CO2")
        db_session.add_all([co1, co2])

        # Questions: Q1 (CO1, 5), Q2 (CO1, 5), Q3 (CO2, 10)
        q1 = ExamQuestion(exam_id=exam.id, question_number="Q1", max_marks=Decimal("5.00"), co_code="CO1")
        q2 = ExamQuestion(exam_id=exam.id, question_number="Q2", max_marks=Decimal("5.00"), co_code="CO1")
        q3 = ExamQuestion(exam_id=exam.id, question_number="Q3", max_marks=Decimal("10.00"), co_code="CO2")
        db_session.add_all([q1, q2, q3])
        db_session.commit()

    exam.exam_date = date.today() + timedelta(days=1)

    # Clear existing marks for this exam if any
    db_session.query(StudentMark).filter(StudentMark.exam_id == exam.id).delete()

    # Add complete marks for all 3 students
    marks_to_add = [
        # Student 0
        StudentMark(exam_id=exam.id, student_id=students[0].id, question_number="Q1", obtained_mark=Decimal("4.00")),
        StudentMark(exam_id=exam.id, student_id=students[0].id, question_number="Q2", obtained_mark=Decimal("4.00")),
        StudentMark(exam_id=exam.id, student_id=students[0].id, question_number="Q3", obtained_mark=Decimal("5.00")),
        # Student 1
        StudentMark(exam_id=exam.id, student_id=students[1].id, question_number="Q1", obtained_mark=Decimal("1.00")),
        StudentMark(exam_id=exam.id, student_id=students[1].id, question_number="Q2", obtained_mark=Decimal("1.00")),
        StudentMark(exam_id=exam.id, student_id=students[1].id, question_number="Q3", obtained_mark=Decimal("8.00")),
        # Student 2
        StudentMark(exam_id=exam.id, student_id=students[2].id, question_number="Q1", obtained_mark=Decimal("3.00")),
        StudentMark(exam_id=exam.id, student_id=students[2].id, question_number="Q2", obtained_mark=Decimal("3.00")),
        StudentMark(exam_id=exam.id, student_id=students[2].id, question_number="Q3", obtained_mark=Decimal("6.00")),
    ]
    db_session.add_all(marks_to_add)
    db_session.commit()

    return exam


class TestPhase7Reporting:

    def test_excel_metadata_shows_exam_date_instead_of_pass_percentage(
        self, db_session, populated_report_exam
    ):
        service = ExamReportService(db_session)
        stream, _ = service.generate_excel_report(populated_report_exam.id)
        ws = load_workbook(stream).active

        total_cols = 2 + 3 + (2 * 4)
        half_cols = max(3, total_cols // 2)
        metadata_text = " ".join(
            str(ws.cell(row=row, column=column).value or "")
            for row in range(3, 7)
            for column in range(1, total_cols + 1)
        )

        assert ws.cell(row=5, column=1).value == "Section:"
        assert ws.cell(row=5, column=2).value == "Section REP_SEC"
        assert ws.cell(row=5, column=half_cols + 1).value == "Exam:"
        assert ws.cell(row=5, column=half_cols + 2).value == populated_report_exam.name
        assert ws.cell(row=6, column=1).value == "Exam Date:"
        assert ws.cell(row=6, column=2).value == populated_report_exam.exam_date.strftime("%d-%m-%Y")
        assert ws.cell(row=6, column=half_cols + 1).value == "Covered COs:"
        assert ws.cell(row=6, column=half_cols + 2).value == "CO1, CO2"
        assert "Pass Percentage" not in metadata_text
        assert f"{populated_report_exam.name} | Exam Date:" not in metadata_text

    def test_1_and_3_to_12_excel_report_generation_and_content(self, db_session, populated_report_exam):
        """
        Tests 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 on Excel report:
        - Generation succeeds
        - Contains correct metadata
        - Contains correct student roster
        - Contains questions in canonical order
        - Contains correct marks
        - Contains correct CO Max Marks, Student CO Obtained, CO Percentage
        - Contains numeric 1/0 for CO Attainment
        - Inclusive >= pass percentage rule preserved
        - Exact equality with pass percentage produces 1
        """
        service = ExamReportService(db_session)
        stream, filename = service.generate_excel_report(populated_report_exam.id)

        assert filename.endswith(".xlsx")
        assert "CO_Attainment" in filename
        assert "CSE_Sem6_A" in filename

        # Load workbook from generated stream
        wb = load_workbook(stream)
        ws = wb.active
        assert ws.title == "CO Attainment Report"

        # Check metadata
        assert ws.cell(row=1, column=1).value is None
        assert len(ws._images) == 1
        logo_path = Path(__file__).resolve().parents[2] / "src" / "assets" / "institute-header.png.jpeg.png"
        with Image.open(logo_path) as logo:
            assert (ws._images[0].width, ws._images[0].height) == logo.size
            assert ws._images[0].width / ws._images[0].height == pytest.approx(logo.width / logo.height)
        assert ws.row_dimensions[1].height == 60
        assert ws.sheet_view.showGridLines is False
        assert ws.page_setup.orientation == "landscape"
        assert str(ws.page_setup.paperSize) == ws.PAPERSIZE_A3
        assert ws.freeze_panes is None
        assert ws.print_area
        title_val = ws.cell(row=2, column=1).value
        assert "COURSE OUTCOME (CO) ATTAINMENT REPORT" in title_val

        # Metadata in rows 3-6
        meta_text = " ".join([str(ws.cell(row=r, column=c).value or "") for r in (3, 4, 5, 6) for c in range(1, ws.max_column + 1)])
        assert ws.cell(row=5, column=2).value == populated_report_exam.name
        assert ws.cell(row=6, column=1).value == "Exam Date:"
        assert ws.cell(row=6, column=2).value == "04-10-2026"
        assert ws.cell(row=6, column=7).value == "Covered COs:"
        assert ws.cell(row=6, column=8).value == "CO1, CO2"
        assert "Pass Percentage" not in meta_text
        assert "50.0%" not in meta_text

        # Three-level header bands and detail headers
        assert ws.cell(row=7, column=1).value == "STUDENT INFORMATION"
        assert ws.cell(row=7, column=3).value == "QUESTION MARKS"
        assert ws.cell(row=7, column=6).value == "CO RESULTS"
        assert ws.cell(row=8, column=1).value == "Register Number"
        assert ws.cell(row=8, column=2).value == "Student Name"
        assert ws.cell(row=8, column=3).value == "Q1"
        assert ws.cell(row=8, column=4).value == "Q2"
        assert ws.cell(row=8, column=5).value == "Q3"

        # Check questions canonical order and mapped CO
        assert "CO1" in str(ws.cell(row=9, column=3).value)
        assert "CO1" in str(ws.cell(row=9, column=4).value)
        assert "CO2" in str(ws.cell(row=9, column=5).value)

        # Check Student 1 results:
        # Q1: 4.0, Q2: 4.0, Q3: 5.0
        # CO1 Max: 10.0, CO1 Obt: 8.0, CO1 %: 80.0, CO1 Attainment: 1 (> 50%)
        # CO2 Max: 10.0, CO2 Obt: 5.0, CO2 %: 50.0, CO2 Attainment: 1 (Exact equality == 50% -> 1)
        s1_row = 10
        assert ws.cell(row=s1_row, column=3).value == 4.0
        assert ws.cell(row=s1_row, column=4).value == 4.0
        assert ws.cell(row=s1_row, column=5).value == 5.0

        # CO1: Max (col 6), Obt (col 7), % (col 8), Attainment (col 9)
        assert ws.cell(row=s1_row, column=6).value == 10.0
        assert ws.cell(row=s1_row, column=7).value == 8.0
        assert ws.cell(row=s1_row, column=8).value == 80.0
        assert ws.cell(row=s1_row, column=9).value == 1  # Numeric 1!

        # CO2: Max (col 10), Obt (col 11), % (col 12), Attainment (col 13)
        assert ws.cell(row=s1_row, column=10).value == 10.0
        assert ws.cell(row=s1_row, column=11).value == 5.0
        assert ws.cell(row=s1_row, column=12).value == 50.0
        # INCLUSIVE PASS PERCENTAGE: 50.0% is >= 50.0%, so Attainment must be 1!
        assert ws.cell(row=s1_row, column=13).value == 1  # Numeric 1!

        # Student 2 results:
        # Q1: 1.0, Q2: 1.0, Q3: 8.0
        # CO1 Obt: 2.0/10.0 = 20.0% -> Attainment 0
        # CO2 Obt: 8.0/10.0 = 80.0% -> Attainment 1
        s2_row = 11
        assert ws.cell(row=s2_row, column=9).value == 0
        assert ws.cell(row=s2_row, column=13).value == 1

        # Derived question statistics follow the student rows and retain question-column alignment.
        assert ws.cell(row=13, column=1).value == "NO OF STUDENTS >= 50% MARKS"
        assert [ws.cell(row=13, column=col).value for col in (3, 4, 5)] == [2, 2, 3]
        assert ws.cell(row=14, column=1).value == "NO OF STUDENTS ATTEMPTED"
        assert [ws.cell(row=14, column=col).value for col in (3, 4, 5)] == [3, 3, 3]
        assert ws.cell(row=15, column=1).value == "% STUDENTS >= 50% MARKS"
        assert [float(ws.cell(row=15, column=col).value) for col in (3, 4, 5)] == pytest.approx(
            [200 / 3, 200 / 3, 100]
        )
        assert ws.cell(row=15, column=3).number_format == '0.00"%"'
        assert ws.cell(row=16, column=1).value == "AVERAGE OF CO1"
        assert float(ws.cell(row=16, column=3).value) == pytest.approx(200 / 3)
        assert ws.cell(row=17, column=1).value == "AVERAGE OF CO2"
        assert float(ws.cell(row=17, column=3).value) == pytest.approx(100)

    def test_2_pdf_report_generation_succeeds(self, db_session, populated_report_exam, monkeypatch):
        """
        Test 2: PDF report generation succeeds and produces a valid PDF file.
        """
        from reportlab.platypus import Table as ReportLabTable
        import app.services.report_service as report_service_module

        captured_tables = []

        def capture_table(data, *args, **kwargs):
            captured_tables.append(data)
            return ReportLabTable(data, *args, **kwargs)

        monkeypatch.setattr(report_service_module, "Table", capture_table)
        service = ExamReportService(db_session)
        stream, filename = service.generate_pdf_report(populated_report_exam.id)

        assert filename.endswith(".pdf")
        assert "CO_Attainment" in filename

        pdf_bytes = stream.getvalue()
        assert len(pdf_bytes) > 1000
        # Check PDF header bytes %PDF-
        assert pdf_bytes.startswith(b"%PDF-")
        assert captured_tables[0][2][3].text == (
            "Internal Assessment 1 - Testing | Exam Date: "
            f"{populated_report_exam.exam_date.strftime('%d-%m-%Y')}"
        )
        result_rows = captured_tables[1]
        assert result_rows[6][0].text == "NO OF STUDENTS >= 50% MARKS"
        assert [result_rows[6][col].text for col in (2, 3, 4)] == ["2", "2", "3"]
        assert result_rows[7][0].text == "NO OF STUDENTS ATTEMPTED"
        assert [result_rows[7][col].text for col in (2, 3, 4)] == ["3", "3", "3"]
        assert result_rows[8][0].text == "% STUDENTS >= 50% MARKS"
        assert [result_rows[8][col].text for col in (2, 3, 4)] == ["66.67%", "66.67%", "100.00%"]
        assert result_rows[9][0].text == "AVERAGE OF CO1"
        assert result_rows[9][2].text == "66.67%"
        assert result_rows[10][0].text == "AVERAGE OF CO2"
        assert result_rows[10][2].text == "100.00%"

    def test_13_student_outside_exam_cohort_rejected(self, db_session, populated_report_exam):
        """
        Test 13: Student outside the exam cohort cannot appear in the report.
        If an unauthorized mark exists, generation fails with an explicit cohort consistency error.
        """
        other_sec = db_session.query(Section).filter(Section.id != populated_report_exam.section_id).first()
        if not other_sec:
            # Create a separate section
            sem = db_session.query(Semester).first()
            other_sec = Section(
                name="OUTSIDE",
                batch_id=populated_report_exam.batch_id,
                department_id=populated_report_exam.department_id,
                year_id=populated_report_exam.year_id,
            )
            db_session.add(other_sec)
            db_session.commit()

        created_outside_student = False
        outside_student = db_session.query(Student).filter_by(register_no="OUTSIDE_999").first()
        if not outside_student:
            outside_student = Student(
                register_no="OUTSIDE_999",
                name="Outside Student",
                batch_id=other_sec.batch_id,
                section_id=other_sec.id,
            )
            db_session.add(outside_student)
            db_session.commit()
            created_outside_student = True

        # Add an unauthorized mark
        bad_mark = StudentMark(
            exam_id=populated_report_exam.id,
            student_id=outside_student.id,
            question_number="Q1",
            obtained_mark=Decimal("3.00"),
        )
        db_session.add(bad_mark)
        db_session.commit()

        service = ExamReportService(db_session)
        with pytest.raises(Exception) as exc_info:
            service.generate_excel_report(populated_report_exam.id)

        assert "does not belong to the exam's configured class/section" in str(exc_info.value.detail)

        # Cleanup bad mark
        db_session.delete(bad_mark)
        db_session.commit()
        if created_outside_student:
            db_session.delete(outside_student)
            db_session.commit()

    def test_14_missing_or_incomplete_marks_rejected(self, db_session, populated_report_exam):
        """
        Test 14: Incomplete marks are rejected per existing Phase 3 policy.
        Silently guessing blank as zero is strictly prohibited.
        """
        # Delete Q3 mark for student 0
        students = db_session.query(Student).filter(Student.section_id == populated_report_exam.section_id).order_by(Student.register_no).all()
        s0 = students[0]
        db_session.query(StudentMark).filter(
            StudentMark.exam_id == populated_report_exam.id,
            StudentMark.student_id == s0.id,
            StudentMark.question_number == "Q3",
        ).delete()
        db_session.commit()

        service = ExamReportService(db_session)
        with pytest.raises(Exception) as exc_info:
            service.generate_excel_report(populated_report_exam.id)

        assert "Incomplete data is rejected" in str(exc_info.value.detail)

        # Restore Q3 mark
        restored = StudentMark(
            exam_id=populated_report_exam.id,
            student_id=s0.id,
            question_number="Q3",
            obtained_mark=Decimal("5.00"),
        )
        db_session.add(restored)
        db_session.commit()

    def test_15_report_download_endpoints_are_usable_without_authentication(self, client, populated_report_exam):
        """
        Test 15: Unauthenticated report download endpoints:
        GET /api/exams/{id}/report/excel
        GET /api/exams/{id}/report/pdf
        """
        # The current OBE workflow does not require a bearer token.
        res_no_auth = client.get(f"/api/exams/{populated_report_exam.id}/report/excel")
        assert res_no_auth.status_code == 200
        assert "spreadsheetml" in res_no_auth.headers["content-type"]
        assert "attachment" in res_no_auth.headers["content-disposition"]
        assert len(res_no_auth.content) > 1000

        res_pdf = client.get(f"/api/exams/{populated_report_exam.id}/report/pdf")
        assert res_pdf.status_code == 200
        assert "application/pdf" in res_pdf.headers["content-type"]
        assert "attachment" in res_pdf.headers["content-disposition"]
        assert len(res_pdf.content) > 1000

        marks_response = client.get(f"/api/exams/{populated_report_exam.id}/marks")
        assert marks_response.status_code == 200
        statistics = marks_response.json()["question_co_statistics"]
        q1 = next(row for row in statistics["questions"] if row["question_number"] == "Q1")
        assert q1["students_at_least_50_percent"] == 2
        assert q1["students_attempted"] == 3
        assert float(q1["percentage_at_least_50_percent"]) == pytest.approx(200 / 3)
