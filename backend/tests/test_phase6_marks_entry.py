"""
Phase 6 Automated Test Suite:
Validates marks entry and CO calculation according to all Phase 6 specifications:
1. Valid mark entry
2. Invalid mark below 0 (negative) rejected
3. Invalid mark above maximum rejected
4. Saving marks
5. Editing marks and recalculating
6. Student cohort consistency (rejects students outside class/section)
7. CO maximum-mark calculation
8. Student CO obtained-mark calculation
9. CO percentage calculation
10. Inclusive >= pass-percentage attainment (1 if >= pass_pct, else 0)
11. Exact equality with pass percentage results in 1
12. Multiple COs in one exam
"""

import unittest
import os
from datetime import date, timedelta
from decimal import Decimal
from app.domain.marks_service import (
    calculate_exam_co_statistics,
    validate_student_cohort,
    validate_and_format_marks,
    process_exam_marks_and_calculate,
    CohortConsistencyError,
)
from app.domain.errors import InvalidMarkError, IncompleteDataError


class TestPhase6MarksEntryAndCOAttainment(unittest.TestCase):
    def setUp(self):
        # Base cohort for Department 1 (CSE), Year 3, Semester 6, Section A
        self.enrolled_students = [
            {"register_no": "TEST-REG-0001", "name": "Sample Student 1"},
            {"register_no": "TEST-REG-0002", "name": "Sample Student 2"},
            {"register_no": "TEST-REG-0003", "name": "Sample Student 3"},
        ]

        # Configured questions for an exam covering CO1 and CO2
        self.configured_questions = [
            {"question_number": "Q1", "max_marks": 2.0, "co_code": "CO1"},
            {"question_number": "Q2", "max_marks": 2.0, "co_code": "CO1"},
            {"question_number": "Q3", "max_marks": 10.0, "co_code": "CO1"},
            {"question_number": "Q4", "max_marks": 2.0, "co_code": "CO2"},
            {"question_number": "Q5", "max_marks": 10.0, "co_code": "CO2"},
        ]

        self.pass_percentage = 50.0

    # 1. Valid mark entry
    def test_valid_mark_entry(self):
        marks = [
            {"register_no": "TEST-REG-0001", "question_number": "Q1", "obtained_mark": 1.5},
            {"register_no": "TEST-REG-0001", "question_number": "Q2", "obtained_mark": 2.0},
        ]
        formatted = validate_and_format_marks(self.configured_questions, marks)
        self.assertEqual(len(formatted), 2)
        self.assertEqual(formatted[0].obtained_mark, 1.5)
        self.assertEqual(formatted[1].obtained_mark, 2.0)

    # 2. Invalid mark below 0
    def test_invalid_mark_below_zero_rejected(self):
        marks = [
            {"register_no": "TEST-REG-0001", "question_number": "Q1", "obtained_mark": -0.5},
        ]
        with self.assertRaises(InvalidMarkError) as ctx:
            validate_and_format_marks(self.configured_questions, marks)
        self.assertIn("cannot be negative", str(ctx.exception))

    # 3. Invalid mark above maximum
    def test_invalid_mark_above_maximum_rejected(self):
        # Q1 max is 2.0, entry is 2.5
        marks = [
            {"register_no": "TEST-REG-0001", "question_number": "Q1", "obtained_mark": 2.5},
        ]
        with self.assertRaises(InvalidMarkError) as ctx:
            validate_and_format_marks(self.configured_questions, marks)
        self.assertIn("exceeds question 'Q1' maximum marks 2.0", str(ctx.exception))

    # 4. Saving marks and calculating results
    def test_saving_marks_and_calculating_results(self):
        marks = [
            {"register_no": "TEST-REG-0001", "question_number": "Q1", "obtained_mark": 2.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q2", "obtained_mark": 2.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q3", "obtained_mark": 8.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q4", "obtained_mark": 1.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q5", "obtained_mark": 5.0},
        ]
        result = process_exam_marks_and_calculate(
            exam_id=1,
            pass_percentage=self.pass_percentage,
            covered_cos=["CO1", "CO2"],
            questions=self.configured_questions,
            enrolled_students=[self.enrolled_students[0]],
            submitted_marks=marks,
            require_complete=True,
        )
        self.assertEqual(result.exam_id, 1)
        self.assertEqual(len(result.students), 1)
        s0 = result.students[0]
        self.assertEqual(s0.register_no, "TEST-REG-0001")
        self.assertEqual(s0.total_obtained, 18.0)

    # 5. Editing marks and recalculating
    def test_editing_marks_recalculates_results(self):
        # Initial: Q3 = 4.0 -> CO1 total = 2+2+4 = 8/14 = 57.14% > 50% -> Attainment 1
        initial_marks = [
            {"register_no": "TEST-REG-0001", "question_number": "Q1", "obtained_mark": 2.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q2", "obtained_mark": 2.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q3", "obtained_mark": 4.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q4", "obtained_mark": 1.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q5", "obtained_mark": 5.0},
        ]
        res1 = process_exam_marks_and_calculate(
            exam_id=1,
            pass_percentage=50.0,
            covered_cos=["CO1", "CO2"],
            questions=self.configured_questions,
            enrolled_students=[self.enrolled_students[0]],
            submitted_marks=initial_marks,
        )
        self.assertEqual(res1.students[0].co_results["CO1"].attainment, 1)

        # Edit: Faculty lowers Q3 mark to 2.0 -> CO1 total = 2+2+2 = 6/14 = 42.85% < 50% -> Attainment becomes 0
        edited_marks = [
            {"register_no": "TEST-REG-0001", "question_number": "Q1", "obtained_mark": 2.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q2", "obtained_mark": 2.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q3", "obtained_mark": 2.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q4", "obtained_mark": 1.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q5", "obtained_mark": 5.0},
        ]
        res2 = process_exam_marks_and_calculate(
            exam_id=1,
            pass_percentage=50.0,
            covered_cos=["CO1", "CO2"],
            questions=self.configured_questions,
            enrolled_students=[self.enrolled_students[0]],
            submitted_marks=edited_marks,
        )
        self.assertEqual(res2.students[0].co_results["CO1"].attainment, 0)
        self.assertAlmostEqual(res2.students[0].co_results["CO1"].obtained_marks, 6.0)

    # 6. Student cohort consistency (rejects student outside section)
    def test_student_outside_cohort_rejected(self):
        marks = [
            {"register_no": "TEST-REG-0999", "question_number": "Q1", "obtained_mark": 2.0},
        ]
        with self.assertRaises(CohortConsistencyError) as ctx:
            validate_student_cohort(self.enrolled_students, marks)
        self.assertIn("does not belong to the exam's configured class/section cohort", str(ctx.exception))

    # 7. CO maximum-mark calculation
    def test_co_maximum_mark_calculation(self):
        # Questions: Q1(2m, CO1) + Q2(2m, CO1) + Q3(10m, CO1) -> CO1 Max = 14m
        # Q4(2m, CO2) + Q5(10m, CO2) -> CO2 Max = 12m
        marks = [
            {"register_no": "TEST-REG-0001", "question_number": "Q1", "obtained_mark": 1.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q2", "obtained_mark": 1.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q3", "obtained_mark": 5.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q4", "obtained_mark": 1.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q5", "obtained_mark": 5.0},
        ]
        result = process_exam_marks_and_calculate(
            exam_id=1,
            pass_percentage=50.0,
            covered_cos=["CO1", "CO2"],
            questions=self.configured_questions,
            enrolled_students=[self.enrolled_students[0]],
            submitted_marks=marks,
        )
        self.assertAlmostEqual(result.co_max_marks["CO1"], 14.0)
        self.assertAlmostEqual(result.co_max_marks["CO2"], 12.0)

    # 8. Student CO obtained-mark calculation
    def test_student_co_obtained_mark_calculation(self):
        marks = [
            {"register_no": "TEST-REG-0001", "question_number": "Q1", "obtained_mark": 2.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q2", "obtained_mark": 1.5},
            {"register_no": "TEST-REG-0001", "question_number": "Q3", "obtained_mark": 7.5},
            {"register_no": "TEST-REG-0001", "question_number": "Q4", "obtained_mark": 2.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q5", "obtained_mark": 8.0},
        ]
        result = process_exam_marks_and_calculate(
            exam_id=1,
            pass_percentage=50.0,
            covered_cos=["CO1", "CO2"],
            questions=self.configured_questions,
            enrolled_students=[self.enrolled_students[0]],
            submitted_marks=marks,
        )
        s = result.students[0]
        # CO1: 2.0 + 1.5 + 7.5 = 11.0
        self.assertAlmostEqual(s.co_results["CO1"].obtained_marks, 11.0)
        # CO2: 2.0 + 8.0 = 10.0
        self.assertAlmostEqual(s.co_results["CO2"].obtained_marks, 10.0)

    # 9. CO percentage calculation
    def test_co_percentage_calculation(self):
        marks = [
            {"register_no": "TEST-REG-0001", "question_number": "Q1", "obtained_mark": 2.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q2", "obtained_mark": 2.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q3", "obtained_mark": 3.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q4", "obtained_mark": 1.5},
            {"register_no": "TEST-REG-0001", "question_number": "Q5", "obtained_mark": 4.5},
        ]
        result = process_exam_marks_and_calculate(
            exam_id=1,
            pass_percentage=50.0,
            covered_cos=["CO1", "CO2"],
            questions=self.configured_questions,
            enrolled_students=[self.enrolled_students[0]],
            submitted_marks=marks,
        )
        s = result.students[0]
        # CO1: 7.0 / 14.0 * 100 = 50.0%
        self.assertAlmostEqual(s.co_results["CO1"].co_percentage, 50.0)
        # CO2: 6.0 / 12.0 * 100 = 50.0%
        self.assertAlmostEqual(s.co_results["CO2"].co_percentage, 50.0)

    # 10. Inclusive pass-percentage attainment (1 if >= pass_pct, else 0)
    def test_exam_co_statistics_use_attempted_marks_and_question_thresholds(self):
        questions = [
            {"question_number": "Q1", "max_marks": 10, "co_code": "CO1"},
            {"question_number": "Q2", "max_marks": 2, "co_code": "CO1"},
            {"question_number": "Q3", "max_marks": 13, "co_code": "CO2"},
            {"question_number": "Q4", "max_marks": 8, "co_code": "CO3"},
        ]
        students = [{"register_no": f"S{number}"} for number in range(1, 4)]
        marks = [
            {"register_no": "S1", "question_number": "Q1", "obtained_mark": "5"},
            {"register_no": "S2", "question_number": "Q1", "obtained_mark": "4"},
            {"register_no": "S1", "question_number": "Q2", "obtained_mark": "1"},
            {"register_no": "S2", "question_number": "Q2", "obtained_mark": "2"},
            {"register_no": "S3", "question_number": "Q2", "obtained_mark": "0"},
            {"register_no": "S3", "question_number": "Q3", "obtained_mark": "6.5"},
        ]

        statistics = calculate_exam_co_statistics(questions, students, marks)
        by_question = {row["question_number"]: row for row in statistics["questions"]}
        by_co = {row["co_code"]: row["average_percentage"] for row in statistics["co_averages"]}

        self.assertEqual(by_question["Q1"]["students_at_least_50_percent"], 1)
        self.assertEqual(by_question["Q1"]["students_attempted"], 2)
        self.assertEqual(by_question["Q1"]["percentage_at_least_50_percent"], Decimal("50"))
        self.assertEqual(by_question["Q2"]["students_at_least_50_percent"], 2)
        self.assertEqual(by_question["Q2"]["students_attempted"], 3)
        self.assertAlmostEqual(float(by_question["Q2"]["percentage_at_least_50_percent"]), 200 / 3)
        self.assertEqual(by_question["Q3"]["students_at_least_50_percent"], 1)
        self.assertEqual(by_question["Q3"]["students_attempted"], 1)
        self.assertEqual(by_question["Q3"]["percentage_at_least_50_percent"], Decimal("100"))
        self.assertEqual(by_question["Q4"]["students_at_least_50_percent"], 0)
        self.assertEqual(by_question["Q4"]["students_attempted"], 0)
        self.assertIsNone(by_question["Q4"]["percentage_at_least_50_percent"])
        self.assertAlmostEqual(float(by_co["CO1"]), (50 + 200 / 3) / 2)
        self.assertEqual(by_co["CO2"], Decimal("100"))
        self.assertIsNone(by_co["CO3"])
        self.assertNotIn("CO4", by_co)

    def test_question_statistics_exclude_blank_marks_but_count_zero_as_attempted(self):
        questions = [{"question_number": "Q1", "max_marks": 10, "co_code": "CO1"}]
        students = [{"register_no": f"S{number}"} for number in range(1, 65)]
        marks = [
            {"register_no": f"S{number}", "question_number": "Q1", "obtained_mark": 5}
            for number in range(1, 21)
        ]
        marks.extend(
            {"register_no": f"S{number}", "question_number": "Q1", "obtained_mark": 0}
            for number in range(21, 26)
        )
        marks.extend(
            {"register_no": f"S{number}", "question_number": "Q1", "obtained_mark": 4}
            for number in range(26, 51)
        )
        marks.extend([
            {"register_no": "S51", "question_number": "Q1", "obtained_mark": None},
            {"register_no": "S52", "question_number": "Q1", "obtained_mark": ""},
            {"register_no": "S53", "question_number": "Q1", "obtained_mark": "   "},
            {"register_no": "S54", "question_number": "Q1"},
        ])

        statistics = calculate_exam_co_statistics(questions, students, marks)
        question = statistics["questions"][0]

        self.assertEqual(question["students_attempted"], 50)
        self.assertEqual(question["students_at_least_50_percent"], 20)
        self.assertEqual(question["percentage_at_least_50_percent"], Decimal("40"))

    def test_strict_greater_than_pass_percentage_attainment(self):
        # Pass threshold = 50.0%
        # CO1: 8.0 / 14.0 = 57.14% > 50.0% -> 1
        # CO2: 5.0 / 12.0 = 41.67% < 50.0% -> 0
        marks = [
            {"register_no": "TEST-REG-0001", "question_number": "Q1", "obtained_mark": 2.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q2", "obtained_mark": 2.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q3", "obtained_mark": 4.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q4", "obtained_mark": 1.0},
            {"register_no": "TEST-REG-0001", "question_number": "Q5", "obtained_mark": 4.0},
        ]
        result = process_exam_marks_and_calculate(
            exam_id=1,
            pass_percentage=50.0,
            covered_cos=["CO1", "CO2"],
            questions=self.configured_questions,
            enrolled_students=[self.enrolled_students[0]],
            submitted_marks=marks,
        )
        s = result.students[0]
        self.assertEqual(s.co_results["CO1"].attainment, 1)
        self.assertEqual(s.co_results["CO2"].attainment, 0)
        # Ensure return type is int 1 or 0
        self.assertIsInstance(s.co_results["CO1"].attainment, int)
        self.assertNotIsInstance(s.co_results["CO1"].attainment, bool)

    # 11. Exact equality with pass percentage resulting in 1
    def test_exact_equality_with_pass_percentage_results_in_one(self):
        # Questions summing to 10 marks for CO1
        q_single = [{"question_number": "Q1", "max_marks": 10.0, "co_code": "CO1"}]
        # Mark 5.0 / 10.0 = exactly 50.0%. Pass Percentage = 50.0%.
        marks = [{"register_no": "TEST-REG-0001", "question_number": "Q1", "obtained_mark": 5.0}]

        result = process_exam_marks_and_calculate(
            exam_id=1,
            pass_percentage=50.0,
            covered_cos=["CO1"],
            questions=q_single,
            enrolled_students=[self.enrolled_students[0]],
            submitted_marks=marks,
        )
        s = result.students[0]
        self.assertAlmostEqual(s.co_results["CO1"].co_percentage, 50.0)
        # The workbook threshold is inclusive, so exact equality attains the CO.
        self.assertEqual(s.co_results["CO1"].attainment, 1)

        # Confirm that 50.01% yields attainment 1
        marks_above = [{"register_no": "TEST-REG-0001", "question_number": "Q1", "obtained_mark": 5.01}]
        res_above = process_exam_marks_and_calculate(
            exam_id=1,
            pass_percentage=50.0,
            covered_cos=["CO1"],
            questions=q_single,
            enrolled_students=[self.enrolled_students[0]],
            submitted_marks=marks_above,
        )
        self.assertEqual(res_above.students[0].co_results["CO1"].attainment, 1)

    # 12. Multiple COs in one exam
    def test_multiple_cos_in_one_exam(self):
        # 3 COs in one exam: CO1, CO2, CO3
        questions_3_cos = [
            {"question_number": "Q1", "max_marks": 10.0, "co_code": "CO1"},
            {"question_number": "Q2", "max_marks": 10.0, "co_code": "CO2"},
            {"question_number": "Q3", "max_marks": 10.0, "co_code": "CO3"},
        ]
        marks = [
            {"register_no": "TEST-REG-0001", "question_number": "Q1", "obtained_mark": 6.0},  # 60% > 50% -> 1
            {"register_no": "TEST-REG-0001", "question_number": "Q2", "obtained_mark": 5.0},  # 50% == 50% -> 1
            {"register_no": "TEST-REG-0001", "question_number": "Q3", "obtained_mark": 4.0},  # 40% < 50% -> 0
        ]
        result = process_exam_marks_and_calculate(
            exam_id=99,
            pass_percentage=50.0,
            covered_cos=["CO1", "CO2", "CO3"],
            questions=questions_3_cos,
            enrolled_students=[self.enrolled_students[0]],
            submitted_marks=marks,
        )
        self.assertEqual(len(result.covered_cos), 3)
        s = result.students[0]
        self.assertEqual(s.co_results["CO1"].attainment, 1)
        self.assertEqual(s.co_results["CO2"].attainment, 1)
        self.assertEqual(s.co_results["CO3"].attainment, 0)


class TestFastAPIMarksEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from app.main import app
        cls.client = TestClient(app)
        resp = cls.client.post(
            "/api/auth/login",
            json={"username": "faculty1", "password": os.environ["OBE_SEED_FACULTY_PASSWORD"]},
        )
        token = resp.json()["access_token"]
        cls.headers = {"Authorization": f"Bearer {token}"}

        # Create a dedicated test exam
        depts = cls.client.get("/api/departments", headers=cls.headers).json()
        cse = next(d for d in depts if d["code"] == "CSE")
        years = cls.client.get("/api/academic/years", headers=cls.headers).json()
        year_3 = next(y for y in years if y["year_number"] == 3)
        semesters = cls.client.get(f"/api/academic/semesters?year_id={year_3['id']}", headers=cls.headers).json()
        sem_6 = next(s for s in semesters if s["semester_number"] == 6)
        sections = cls.client.get(
            f"/api/academic/sections?department_id={cse['id']}&year_id={year_3['id']}",
            headers=cls.headers,
        ).json()
        sec_a = next(s for s in sections if s["name"] == "A")
        cls.section_id = sec_a["id"]
        subjects = cls.client.get(
            f"/api/subjects?department_id={cse['id']}&year_id={year_3['id']}&semester_id={sem_6['id']}",
            headers=cls.headers,
        ).json()
        subject = next(s for s in subjects if s["name"] == "WEB TECHNOLOGIES")
        cls.subject_id = subject["id"]

        exam_payload = {
            "name": "Phase 6 Integration Exam",
            "exam_type": "CUSTOM",
            "exam_date": (date.today() + timedelta(days=1)).isoformat(),
            "department_id": cse["id"],
            "year_id": year_3["id"],
            "semester_id": sem_6["id"],
            "section_id": sec_a["id"],
            "subject_id": subject["id"],
            "pass_percentage": 50.0,
            "covered_cos": ["CO1", "CO2"],
            "questions": [
                {"question_number": "Q1", "max_marks": 5.0, "co_code": "CO1"},
                {"question_number": "Q2", "max_marks": 5.0, "co_code": "CO2"},
            ],
        }
        res = cls.client.post("/api/exams", json=exam_payload, headers=cls.headers)
        cls.exam_id = res.json()["id"]

    def test_fastapi_exam_roster_endpoint(self):
        resp = self.client.get(f"/api/exams/{self.exam_id}/roster", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        roster = resp.json()
        self.assertGreater(len(roster), 0)
        self.assertTrue(any(s["register_no"] == "TEST-REG-0001" for s in roster))

    def test_fastapi_exam_questions_endpoint(self):
        resp = self.client.get(f"/api/exams/{self.exam_id}/questions", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        questions = resp.json()
        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0]["question_number"], "Q1")
        self.assertEqual(questions[1]["question_number"], "Q2")

    def test_fastapi_marks_save_valid(self):
        payload = {
            "marks": [
                {"register_no": "TEST-REG-0001", "question_number": "Q1", "obtained_mark": 4.0},  # 80% > 50% -> 1
                {"register_no": "TEST-REG-0001", "question_number": "Q2", "obtained_mark": 2.0},  # 40% < 50% -> 0
            ]
        }
        resp = self.client.post(f"/api/exams/{self.exam_id}/marks", json=payload, headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        calc = data["calculation_result"]
        student = next(s for s in calc["students"] if s["register_no"] == "TEST-REG-0001")
        self.assertEqual(student["co_results"]["CO1"]["attainment"], 1)
        self.assertEqual(student["co_results"]["CO2"]["attainment"], 0)

    def test_fastapi_deterministic_55_percent_runtime_chain(self):
        exam_payload = {
            "name": "Deterministic 55 Percent Verification",
            "exam_type": "CUSTOM",
            "exam_date": (date.today() + timedelta(days=1)).isoformat(),
            "department_id": 1,
            "year_id": 3,
            "semester_id": 6,
            "section_id": self.section_id,
            "subject_id": self.subject_id,
            "pass_percentage": 55.0,
            "covered_cos": ["CO1"],
            "questions": [
                {"question_number": "Q1", "max_marks": 10.0, "co_code": "CO1"},
                {"question_number": "Q2", "max_marks": 10.0, "co_code": "CO1"},
            ],
        }
        exam_response = self.client.post("/api/exams", json=exam_payload, headers=self.headers)
        self.assertEqual(exam_response.status_code, 201)
        exam_id = exam_response.json()["id"]
        roster = self.client.get(f"/api/exams/{exam_id}/roster", headers=self.headers).json()
        marks = []
        for index, student in enumerate(roster):
            value = 5.5 if index == 0 else 0.0
            marks.extend([
                {"register_no": student["register_no"], "question_number": "Q1", "obtained_mark": value},
                {"register_no": student["register_no"], "question_number": "Q2", "obtained_mark": value},
            ])

        response = self.client.post(
            f"/api/exams/{exam_id}/marks?require_complete=true",
            json={"marks": marks},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()["calculation_result"]
        exact = next(student for student in result["students"] if student["register_no"] == roster[0]["register_no"])
        below = next(student for student in result["students"] if student["register_no"] == roster[1]["register_no"])
        self.assertAlmostEqual(exact["co_results"]["CO1"]["co_percentage"], 55.0)
        self.assertEqual(exact["co_results"]["CO1"]["attainment"], 1)
        self.assertEqual(below["co_results"]["CO1"]["attainment"], 0)
        overall = result["overall_co_attainment"]["CO1"]
        self.assertEqual(overall["total_students"], len(roster))
        self.assertEqual(overall["students_attaining_co"], 1)

    def test_fastapi_marks_save_negative_rejected(self):
        payload = {
            "marks": [
                {"register_no": "TEST-REG-0001", "question_number": "Q1", "obtained_mark": -1.0},
            ]
        }
        resp = self.client.post(f"/api/exams/{self.exam_id}/marks", json=payload, headers=self.headers)
        self.assertEqual(resp.status_code, 422)  # Pydantic ge=0.0 rejects or domain rejects

    def test_fastapi_marks_save_exceeds_max_rejected(self):
        payload = {
            "marks": [
                {"register_no": "TEST-REG-0001", "question_number": "Q1", "obtained_mark": 10.0},  # Max is 5.0
            ]
        }
        resp = self.client.post(f"/api/exams/{self.exam_id}/marks", json=payload, headers=self.headers)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("exceeds question", resp.json()["detail"])

    def test_fastapi_marks_save_outside_cohort_rejected(self):
        payload = {
            "marks": [
                {"register_no": "99UNKNOWN01", "question_number": "Q1", "obtained_mark": 3.0},
            ]
        }
        resp = self.client.post(f"/api/exams/{self.exam_id}/marks", json=payload, headers=self.headers)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("does not belong to the exam's configured class/section", resp.json()["detail"])

    def test_fastapi_marks_get_reload_and_recalculate(self):
        # 1. Save initial marks
        save_payload = {
            "marks": [
                {"register_no": "TEST-REG-0001", "question_number": "Q1", "obtained_mark": 4.0},
                {"register_no": "TEST-REG-0001", "question_number": "Q2", "obtained_mark": 1.0},
            ]
        }
        self.client.post(f"/api/exams/{self.exam_id}/marks", json=save_payload, headers=self.headers)

        # 2. Reload and verify results
        resp = self.client.get(f"/api/exams/{self.exam_id}/marks", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["exam_id"], self.exam_id)
        self.assertIsNotNone(data["calculation_result"])
        student = next(s for s in data["calculation_result"]["students"] if s["register_no"] == "TEST-REG-0001")
        self.assertEqual(student["co_results"]["CO1"]["attainment"], 1)  # 4/5 = 80% > 50%
        self.assertEqual(student["co_results"]["CO2"]["attainment"], 0)  # 1/5 = 20% < 50%

        # 3. Edit marks and verify recalculation
        edit_payload = {
            "marks": [
                {"register_no": "TEST-REG-0001", "question_number": "Q1", "obtained_mark": 1.0},  # now 20% -> 0
                {"register_no": "TEST-REG-0001", "question_number": "Q2", "obtained_mark": 4.0},  # now 80% -> 1
            ]
        }
        edit_resp = self.client.post(f"/api/exams/{self.exam_id}/marks", json=edit_payload, headers=self.headers)
        self.assertEqual(edit_resp.status_code, 200)
        reloaded_student = next(s for s in edit_resp.json()["calculation_result"]["students"] if s["register_no"] == "TEST-REG-0001")
        self.assertEqual(reloaded_student["co_results"]["CO1"]["attainment"], 0)
        self.assertEqual(reloaded_student["co_results"]["CO2"]["attainment"], 1)

    def test_fastapi_internal_1_uses_question_ids_for_all_thirteen_questions(self):
        exam_payload = {
            "name": "Internal Assessment 1 Question Identity Regression",
            "exam_type": "INTERNAL_1",
            "exam_date": (date.today() + timedelta(days=1)).isoformat(),
            "department_id": 1,
            "year_id": 3,
            "semester_id": 6,
            "section_id": self.section_id,
            "subject_id": self.subject_id,
            "pass_percentage": 50.0,
            "covered_cos": ["CO1", "CO2"],
            "questions": [
                {"question_number": f"Q{i}", "max_marks": 2.0, "co_code": "CO1" if i <= 5 else "CO2"}
                for i in range(1, 11)
            ] + [
                {"question_number": "Q11", "max_marks": 10.0, "co_code": "CO1"},
                {"question_number": "Q12", "max_marks": 10.0, "co_code": "CO2"},
                {"question_number": "Q13", "max_marks": 10.0, "co_code": "CO1"},
            ],
        }
        exam_response = self.client.post("/api/exams", json=exam_payload, headers=self.headers)
        self.assertEqual(exam_response.status_code, 201)
        exam_id = exam_response.json()["id"]

        questions_response = self.client.get(f"/api/exams/{exam_id}/questions", headers=self.headers)
        self.assertEqual(questions_response.status_code, 200)
        questions = questions_response.json()
        self.assertEqual([q["question_number"] for q in questions], [f"Q{i}" for i in range(1, 14)])
        self.assertEqual(len({q["id"] for q in questions}), 13)

        marks = []
        for question in questions:
            mark = 1.0 if question["question_number"] in {f"Q{i}" for i in range(1, 11)} else 5.0
            marks.append({
                "register_no": "TEST-REG-0001",
                "question_id": question["id"],
                "obtained_mark": mark,
            })

        response = self.client.post(
            f"/api/exams/{exam_id}/marks?require_complete=false",
            json={"marks": marks},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()["calculation_result"]
        student = next(s for s in result["students"] if s["register_no"] == "TEST-REG-0001")
        self.assertEqual(result["co_max_marks"], {"CO1": 30.0, "CO2": 20.0})
        self.assertEqual(student["co_results"]["CO1"]["obtained_marks"], 15.0)
        self.assertEqual(student["co_results"]["CO1"]["co_percentage"], 50.0)
        self.assertEqual(student["co_results"]["CO1"]["attainment"], 1)
        self.assertEqual(student["co_results"]["CO2"]["obtained_marks"], 10.0)
        self.assertEqual(student["co_results"]["CO2"]["co_percentage"], 50.0)
        self.assertEqual(student["co_results"]["CO2"]["attainment"], 1)

        edited_marks = [
            {**mark, "obtained_mark": 0.0}
            if mark["question_id"] == questions[4]["id"] else mark
            for mark in marks
        ]
        edit_response = self.client.post(
            f"/api/exams/{exam_id}/marks?require_complete=false",
            json={"marks": edited_marks},
            headers=self.headers,
        )
        self.assertEqual(edit_response.status_code, 200)
        edited_student = next(
            s for s in edit_response.json()["calculation_result"]["students"]
            if s["register_no"] == "TEST-REG-0001"
        )
        self.assertAlmostEqual(edited_student["co_results"]["CO1"]["obtained_marks"], 14.0)
        self.assertAlmostEqual(edited_student["co_results"]["CO1"]["co_percentage"], 46.6666666667)
        self.assertEqual(edited_student["co_results"]["CO1"]["attainment"], 0)

        reload_response = self.client.get(f"/api/exams/{exam_id}/marks", headers=self.headers)
        self.assertEqual(reload_response.status_code, 200)
        saved_marks = reload_response.json()["marks"]
        self.assertEqual({mark["question_id"] for mark in saved_marks}, {q["id"] for q in questions})
        reloaded_student = next(
            s for s in reload_response.json()["calculation_result"]["students"]
            if s["register_no"] == "TEST-REG-0001"
        )
        self.assertEqual(reloaded_student["co_results"]["CO1"]["attainment"], 0)


if __name__ == "__main__":
    unittest.main()
