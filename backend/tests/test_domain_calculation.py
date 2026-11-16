"""
Unit tests for Pure CO Domain Model and Authoritative Calculation Engine.
Covers all 20 required verification scenarios, manual department test, and domain validations.
"""

import unittest
from app.domain.models import (
    Question,
    Student,
    StudentQuestionMark,
    ExamCalculationInput,
)
from app.domain.engine import (
    calculate_exam_co_attainment,
    validate_calculation_input,
)
from app.domain.errors import (
    InvalidExamConfigurationError,
    InvalidQuestionConfigurationError,
    InvalidMarkError,
    IncompleteDataError,
    DomainValidationError,
)


class TestCOCalculationEngine(unittest.TestCase):
    def setUp(self):
        """Standard valid base fixtures for test construction."""
        self.default_student = Student(register_no="TEST-REG-0001", name="Sample Student 1")
        self.default_questions = [
            Question(question_number="1", max_marks=2.0, mapped_co="CO1"),
            Question(question_number="2", max_marks=2.0, mapped_co="CO1"),
            Question(question_number="11", max_marks=10.0, mapped_co="CO1"),
        ]

    # 1. Student above pass percentage -> attainment 1
    def test_student_above_pass_percentage_attainment_1(self):
        questions = [
            Question(question_number="1", max_marks=10.0, mapped_co="CO1"),
        ]
        students = [self.default_student]
        # 6.0 out of 10.0 = 60.0% > 55.0%
        marks = [StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=6.0)]
        inp = ExamCalculationInput(
            exam_id="EXAM_1",
            pass_percentage=55.0,
            covered_cos=["CO1"],
            questions=questions,
            students=students,
            marks=marks,
        )
        res = calculate_exam_co_attainment(inp)
        co1 = res.students[0].co_results["CO1"]
        self.assertAlmostEqual(co1.co_percentage, 60.0)
        self.assertEqual(co1.attainment, 1)

    # 2. Student below pass percentage -> attainment 0
    def test_student_below_pass_percentage_attainment_0(self):
        questions = [
            Question(question_number="1", max_marks=10.0, mapped_co="CO1"),
        ]
        students = [self.default_student]
        # 5.0 out of 10.0 = 50.0% < 55.0%
        marks = [StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=5.0)]
        inp = ExamCalculationInput(
            exam_id="EXAM_1",
            pass_percentage=55.0,
            covered_cos=["CO1"],
            questions=questions,
            students=students,
            marks=marks,
        )
        res = calculate_exam_co_attainment(inp)
        co1 = res.students[0].co_results["CO1"]
        self.assertAlmostEqual(co1.co_percentage, 50.0)
        self.assertEqual(co1.attainment, 0)

    # 3. Student threshold boundaries use the workbook's inclusive rule.
    def test_student_exactly_equal_to_pass_percentage_inclusive_threshold(self):
        questions = [
            Question(question_number="1", max_marks=100.0, mapped_co="CO1"),
        ]
        students = [self.default_student]
        # 54.99 out of 100.0 is below the threshold.
        marks_below = [StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=54.99)]
        inp_below = ExamCalculationInput(
            exam_id="EXAM_1",
            pass_percentage=55.0,
            covered_cos=["CO1"],
            questions=questions,
            students=students,
            marks=marks_below,
        )
        res_below = calculate_exam_co_attainment(inp_below)
        self.assertAlmostEqual(res_below.students[0].co_results["CO1"].co_percentage, 54.99)
        self.assertEqual(res_below.students[0].co_results["CO1"].attainment, 0)

        # 55.0 out of 100.0 = exactly 55.0%, and is attained.
        marks = [StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=55.0)]
        inp = ExamCalculationInput(
            exam_id="EXAM_1",
            pass_percentage=55.0,
            covered_cos=["CO1"],
            questions=questions,
            students=students,
            marks=marks,
        )
        res = calculate_exam_co_attainment(inp)
        co1 = res.students[0].co_results["CO1"]
        self.assertAlmostEqual(co1.co_percentage, 55.0)
        self.assertEqual(co1.attainment, 1)

        # 55.01% is also attained.
        marks_just_above = [StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=55.01)]
        inp_above = ExamCalculationInput(
            exam_id="EXAM_1",
            pass_percentage=55.0,
            covered_cos=["CO1"],
            questions=questions,
            students=students,
            marks=marks_just_above,
        )
        res_above = calculate_exam_co_attainment(inp_above)
        self.assertEqual(res_above.students[0].co_results["CO1"].attainment, 1)

    # 4. Multiple questions mapped to the same CO
    def test_multiple_questions_mapped_to_same_co(self):
        questions = [
            Question(question_number="1", max_marks=2.0, mapped_co="CO1"),
            Question(question_number="2", max_marks=2.0, mapped_co="CO1"),
            Question(question_number="3", max_marks=2.0, mapped_co="CO1"),
            Question(question_number="11", max_marks=10.0, mapped_co="CO1"),
        ]
        students = [self.default_student]
        # Q1=2, Q2=1.5, Q3=2, Q11=8 -> Total = 13.5 / 16.0 = 84.375%
        marks = [
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=2.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="2", obtained_mark=1.5),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="3", obtained_mark=2.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="11", obtained_mark=8.0),
        ]
        inp = ExamCalculationInput(
            exam_id="EXAM_1",
            pass_percentage=55.0,
            covered_cos=["CO1"],
            questions=questions,
            students=students,
            marks=marks,
        )
        res = calculate_exam_co_attainment(inp)
        co1 = res.students[0].co_results["CO1"]
        self.assertAlmostEqual(co1.co_max_marks, 16.0)
        self.assertAlmostEqual(co1.obtained_marks, 13.5)
        self.assertAlmostEqual(co1.co_percentage, 84.375)
        self.assertEqual(co1.attainment, 1)

    # 5. Different maximum marks for different questions
    def test_different_maximum_marks_for_questions(self):
        questions = [
            Question(question_number="1", max_marks=2.0, mapped_co="CO1"),
            Question(question_number="11", max_marks=8.0, mapped_co="CO1"),
            Question(question_number="12", max_marks=15.0, mapped_co="CO1"),
        ]
        students = [self.default_student]
        marks = [
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=2.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="11", obtained_mark=4.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="12", obtained_mark=10.0),
        ]
        inp = ExamCalculationInput(
            exam_id="EXAM_1",
            pass_percentage=60.0,
            covered_cos=["CO1"],
            questions=questions,
            students=students,
            marks=marks,
        )
        res = calculate_exam_co_attainment(inp)
        co1 = res.students[0].co_results["CO1"]
        self.assertAlmostEqual(co1.co_max_marks, 25.0)
        self.assertAlmostEqual(co1.obtained_marks, 16.0)
        # 16 / 25 * 100 = 64.0% > 60.0%
        self.assertAlmostEqual(co1.co_percentage, 64.0)
        self.assertEqual(co1.attainment, 1)

    # 6. Multiple COs in one exam
    def test_multiple_cos_in_one_exam(self):
        questions = [
            Question(question_number="1", max_marks=2.0, mapped_co="CO1"),
            Question(question_number="2", max_marks=10.0, mapped_co="CO1"),
            Question(question_number="3", max_marks=2.0, mapped_co="CO2"),
            Question(question_number="4", max_marks=10.0, mapped_co="CO2"),
        ]
        students = [self.default_student]
        marks = [
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=2.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="2", obtained_mark=8.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="3", obtained_mark=1.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="4", obtained_mark=4.0),
        ]
        inp = ExamCalculationInput(
            exam_id="EXAM_MULTI_CO",
            pass_percentage=55.0,
            covered_cos=["CO1", "CO2"],
            questions=questions,
            students=students,
            marks=marks,
        )
        res = calculate_exam_co_attainment(inp)
        co1 = res.students[0].co_results["CO1"]
        co2 = res.students[0].co_results["CO2"]

        # CO1: 10 / 12 = 83.333% > 55% -> 1
        self.assertAlmostEqual(co1.co_max_marks, 12.0)
        self.assertAlmostEqual(co1.obtained_marks, 10.0)
        self.assertEqual(co1.attainment, 1)

        # CO2: 5 / 12 = 41.666% < 55% -> 0
        self.assertAlmostEqual(co2.co_max_marks, 12.0)
        self.assertAlmostEqual(co2.obtained_marks, 5.0)
        self.assertEqual(co2.attainment, 0)

    # 7. Multiple students
    def test_multiple_students(self):
        questions = [
            Question(question_number="1", max_marks=10.0, mapped_co="CO1"),
        ]
        students = [
            Student(register_no="TEST-REG-0001", name="Sample Student 1"),
            Student(register_no="TEST-REG-0002", name="Sample Student 7"),
            Student(register_no="TEST-REG-0003", name="Sample Student 8"),
        ]
        marks = [
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=8.0),
            StudentQuestionMark(register_no="TEST-REG-0002", question_number="1", obtained_mark=5.0),
            StudentQuestionMark(register_no="TEST-REG-0003", question_number="1", obtained_mark=9.5),
        ]
        inp = ExamCalculationInput(
            exam_id="EXAM_MULTI_STUDENTS",
            pass_percentage=55.0,
            covered_cos=["CO1"],
            questions=questions,
            students=students,
            marks=marks,
        )
        res = calculate_exam_co_attainment(inp)
        self.assertEqual(len(res.students), 3)

        self.assertEqual(res.students[0].co_results["CO1"].attainment, 1)  # 80% > 55%
        self.assertEqual(res.students[1].co_results["CO1"].attainment, 0)  # 50% < 55%
        self.assertEqual(res.students[2].co_results["CO1"].attainment, 1)  # 95% > 55%

    # 8. Correct CO maximum mark calculation
    def test_correct_co_maximum_mark_calculation(self):
        questions = [
            Question(question_number="1", max_marks=2.0, mapped_co="CO1"),
            Question(question_number="2", max_marks=3.5, mapped_co="CO1"),
            Question(question_number="3", max_marks=10.0, mapped_co="CO2"),
            Question(question_number="4", max_marks=8.5, mapped_co="CO2"),
        ]
        inp = ExamCalculationInput(
            exam_id="EXAM_MAX",
            pass_percentage=50.0,
            covered_cos=["CO1", "CO2"],
            questions=questions,
            students=[self.default_student],
            marks=[
                StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=2.0),
                StudentQuestionMark(register_no="TEST-REG-0001", question_number="2", obtained_mark=3.5),
                StudentQuestionMark(register_no="TEST-REG-0001", question_number="3", obtained_mark=10.0),
                StudentQuestionMark(register_no="TEST-REG-0001", question_number="4", obtained_mark=8.5),
            ],
        )
        res = calculate_exam_co_attainment(inp)
        self.assertAlmostEqual(res.co_max_marks["CO1"], 5.5)
        self.assertAlmostEqual(res.co_max_marks["CO2"], 18.5)

    # 9. Correct CO obtained mark calculation
    def test_correct_co_obtained_mark_calculation(self):
        questions = [
            Question(question_number="1", max_marks=2.0, mapped_co="CO1"),
            Question(question_number="2", max_marks=2.0, mapped_co="CO1"),
            Question(question_number="3", max_marks=10.0, mapped_co="CO1"),
        ]
        marks = [
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=1.5),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="2", obtained_mark=2.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="3", obtained_mark=7.5),
        ]
        inp = ExamCalculationInput(
            exam_id="EXAM_OBT",
            pass_percentage=50.0,
            covered_cos=["CO1"],
            questions=questions,
            students=[self.default_student],
            marks=marks,
        )
        res = calculate_exam_co_attainment(inp)
        co1 = res.students[0].co_results["CO1"]
        self.assertAlmostEqual(co1.obtained_marks, 11.0)
        self.assertAlmostEqual(res.students[0].total_obtained, 11.0)

    # 10. Correct percentage calculation
    def test_correct_percentage_calculation(self):
        questions = [
            Question(question_number="1", max_marks=30.0, mapped_co="CO1"),
        ]
        marks = [
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=12.0),
        ]
        inp = ExamCalculationInput(
            exam_id="EXAM_PCT",
            pass_percentage=50.0,
            covered_cos=["CO1"],
            questions=questions,
            students=[self.default_student],
            marks=marks,
        )
        res = calculate_exam_co_attainment(inp)
        co1 = res.students[0].co_results["CO1"]
        # 12 / 30 * 100 = 40.0%
        self.assertAlmostEqual(co1.co_percentage, 40.0)

    # 11. Negative marks rejected
    def test_negative_marks_rejected(self):
        questions = [Question(question_number="1", max_marks=10.0, mapped_co="CO1")]
        marks = [StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=-0.5)]
        inp = ExamCalculationInput(
            exam_id="EXAM_NEG",
            pass_percentage=50.0,
            covered_cos=["CO1"],
            questions=questions,
            students=[self.default_student],
            marks=marks,
        )
        with self.assertRaises(InvalidMarkError):
            calculate_exam_co_attainment(inp)

    # 12. Marks above question maximum rejected
    def test_marks_above_question_maximum_rejected(self):
        questions = [Question(question_number="1", max_marks=10.0, mapped_co="CO1")]
        marks = [StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=10.5)]
        inp = ExamCalculationInput(
            exam_id="EXAM_EXCEED",
            pass_percentage=50.0,
            covered_cos=["CO1"],
            questions=questions,
            students=[self.default_student],
            marks=marks,
        )
        with self.assertRaises(InvalidMarkError):
            calculate_exam_co_attainment(inp)

    # 13. Missing CO rejected
    def test_missing_co_rejected(self):
        questions = [Question(question_number="1", max_marks=10.0, mapped_co="")]
        inp = ExamCalculationInput(
            exam_id="EXAM_NO_CO",
            pass_percentage=50.0,
            covered_cos=["CO1"],
            questions=questions,
            students=[self.default_student],
            marks=[StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=5.0)],
        )
        with self.assertRaises(InvalidQuestionConfigurationError):
            calculate_exam_co_attainment(inp)

    # 14. Question mapped to uncovered CO rejected
    def test_question_mapped_to_uncovered_co_rejected(self):
        questions = [Question(question_number="1", max_marks=10.0, mapped_co="CO3")]
        inp = ExamCalculationInput(
            exam_id="EXAM_UNCOVERED",
            pass_percentage=50.0,
            covered_cos=["CO1", "CO2"],  # CO3 is NOT covered
            questions=questions,
            students=[self.default_student],
            marks=[StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=5.0)],
        )
        with self.assertRaises(InvalidQuestionConfigurationError):
            calculate_exam_co_attainment(inp)

    # 15. Duplicate question number rejected
    def test_duplicate_question_number_rejected(self):
        questions = [
            Question(question_number="1", max_marks=2.0, mapped_co="CO1"),
            Question(question_number="1", max_marks=2.0, mapped_co="CO1"),  # Duplicate Q1
        ]
        inp = ExamCalculationInput(
            exam_id="EXAM_DUP_Q",
            pass_percentage=50.0,
            covered_cos=["CO1"],
            questions=questions,
            students=[self.default_student],
            marks=[],
        )
        with self.assertRaises(InvalidQuestionConfigurationError):
            calculate_exam_co_attainment(inp)

    # 16. Invalid pass percentage rejected
    def test_invalid_pass_percentage_rejected(self):
        # 0 or negative
        for invalid_pct in [0.0, -10.0, 105.0]:
            with self.subTest(invalid_pct=invalid_pct):
                inp = ExamCalculationInput(
                    exam_id="EXAM_INV_PCT",
                    pass_percentage=invalid_pct,
                    covered_cos=["CO1"],
                    questions=[Question(question_number="1", max_marks=10.0, mapped_co="CO1")],
                    students=[self.default_student],
                    marks=[StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=5.0)],
                )
                with self.assertRaises(InvalidExamConfigurationError):
                    calculate_exam_co_attainment(inp)

    # 17. Zero CO maximum marks rejected
    def test_zero_co_maximum_marks_rejected(self):
        # CO2 is in covered_cos, but has no questions assigned to it
        questions = [
            Question(question_number="1", max_marks=10.0, mapped_co="CO1"),
        ]
        inp = ExamCalculationInput(
            exam_id="EXAM_ZERO_CO",
            pass_percentage=50.0,
            covered_cos=["CO1", "CO2"],  # CO2 has 0 questions mapped
            questions=questions,
            students=[self.default_student],
            marks=[StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=5.0)],
        )
        with self.assertRaises(InvalidExamConfigurationError):
            calculate_exam_co_attainment(inp)

    # 18. Different question-to-CO mappings
    def test_different_question_to_co_mappings(self):
        # Exam A mapping: Q1 -> CO1, Q2 -> CO2
        q_a = [
            Question(question_number="1", max_marks=10.0, mapped_co="CO1"),
            Question(question_number="2", max_marks=10.0, mapped_co="CO2"),
        ]
        marks_a = [
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=8.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="2", obtained_mark=2.0),
        ]
        inp_a = ExamCalculationInput(
            exam_id="EXAM_A",
            pass_percentage=50.0,
            covered_cos=["CO1", "CO2"],
            questions=q_a,
            students=[self.default_student],
            marks=marks_a,
        )
        res_a = calculate_exam_co_attainment(inp_a)
        self.assertEqual(res_a.students[0].co_results["CO1"].attainment, 1)
        self.assertEqual(res_a.students[0].co_results["CO2"].attainment, 0)

        # Exam B mapping: Inverted mapping: Q1 -> CO2, Q2 -> CO1
        q_b = [
            Question(question_number="1", max_marks=10.0, mapped_co="CO2"),
            Question(question_number="2", max_marks=10.0, mapped_co="CO1"),
        ]
        inp_b = ExamCalculationInput(
            exam_id="EXAM_B",
            pass_percentage=50.0,
            covered_cos=["CO1", "CO2"],
            questions=q_b,
            students=[self.default_student],
            marks=marks_a,
        )
        res_b = calculate_exam_co_attainment(inp_b)
        self.assertEqual(res_b.students[0].co_results["CO1"].attainment, 0)  # Q2 = 2.0 / 10 -> 20%
        self.assertEqual(res_b.students[0].co_results["CO2"].attainment, 1)  # Q1 = 8.0 / 10 -> 80%

    # 19. Editing a student's question mark and recalculating the result
    def test_editing_mark_recalculates_result_consistently(self):
        questions = [Question(question_number="1", max_marks=10.0, mapped_co="CO1")]
        students = [self.default_student]

        # Initial mark: 5.0 / 10.0 = 50.0% <= 55.0% -> Attainment 0
        marks_v1 = [StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=5.0)]
        inp_v1 = ExamCalculationInput(
            exam_id="EXAM_EDIT",
            pass_percentage=55.0,
            covered_cos=["CO1"],
            questions=questions,
            students=students,
            marks=marks_v1,
        )
        res_v1 = calculate_exam_co_attainment(inp_v1)
        self.assertEqual(res_v1.students[0].co_results["CO1"].attainment, 0)

        # Edited mark: changed to 7.0 / 10.0 = 70.0% >= 55.0% -> Attainment 1
        marks_v2 = [StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=7.0)]
        inp_v2 = ExamCalculationInput(
            exam_id="EXAM_EDIT",
            pass_percentage=55.0,
            covered_cos=["CO1"],
            questions=questions,
            students=students,
            marks=marks_v2,
        )
        res_v2 = calculate_exam_co_attainment(inp_v2)
        self.assertEqual(res_v2.students[0].co_results["CO1"].attainment, 1)
        self.assertAlmostEqual(res_v2.students[0].co_results["CO1"].obtained_marks, 7.0)
        self.assertAlmostEqual(res_v2.students[0].co_results["CO1"].co_percentage, 70.0)

    # 20. Incomplete/unresolved mark scenarios are handled explicitly without inventing a policy
    def test_incomplete_mark_scenarios_handled_explicitly(self):
        questions = [
            Question(question_number="1", max_marks=5.0, mapped_co="CO1"),
            Question(question_number="2", max_marks=5.0, mapped_co="CO1"),
        ]
        students = [self.default_student]
        # Only Q1 mark is provided; Q2 mark is missing
        partial_marks = [
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=4.0),
        ]
        inp = ExamCalculationInput(
            exam_id="EXAM_INCOMPLETE",
            pass_percentage=55.0,
            covered_cos=["CO1"],
            questions=questions,
            students=students,
            marks=partial_marks,
        )
        # By default, engine raises IncompleteDataError rather than guessing an absence policy or zero mark
        with self.assertRaises(IncompleteDataError):
            calculate_exam_co_attainment(inp, require_complete_marks=True)

    # Manual verification test based on the department's real workbook-style calculation
    def test_manual_verification_department_real_workbook_values(self):
        """
        Department workbook scenario:
        CO2 maximum marks = 34
        Student CO2 obtained marks = 29
        CO2 percentage = 29 / 34 * 100 = 85.2941176...%
        Pass Percentage = 55.0%
        Verify attainment == 1.

        Second CO (CO3):
        CO3 maximum marks = 16
        Student CO3 obtained marks = 6
        CO3 percentage = 6 / 16 * 100 = 37.5%
        Pass Percentage = 55.0%
        Verify attainment == 0.
        """
        # Configure questions to match CO2 (34 marks) and CO3 (16 marks)
        # e.g. from int-II sheet: Q1-Q6 (2m each) + Q11, Q12 etc.
        questions = [
            # CO2 questions summing to 34 marks
            Question(question_number="1", max_marks=2.0, mapped_co="CO2"),
            Question(question_number="2", max_marks=2.0, mapped_co="CO2"),
            Question(question_number="3", max_marks=10.0, mapped_co="CO2"),
            Question(question_number="4", max_marks=10.0, mapped_co="CO2"),
            Question(question_number="5", max_marks=10.0, mapped_co="CO2"),
            # CO3 questions summing to 16 marks
            Question(question_number="6", max_marks=6.0, mapped_co="CO3"),
            Question(question_number="7", max_marks=10.0, mapped_co="CO3"),
        ]
        student = Student(register_no="TEST-REG-0001", name="Sample Student 6")

        # Student obtains 29 in CO2: 2 + 2 + 9 + 8 + 8 = 29
        # Student obtains 6 in CO3: 2 + 4 = 6
        marks = [
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=2.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="2", obtained_mark=2.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="3", obtained_mark=9.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="4", obtained_mark=8.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="5", obtained_mark=8.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="6", obtained_mark=2.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="7", obtained_mark=4.0),
        ]

        inp = ExamCalculationInput(
            exam_id="INT_II_WORKBOOK",
            pass_percentage=55.0,
            covered_cos=["CO2", "CO3"],
            questions=questions,
            students=[student],
            marks=marks,
        )

        result = calculate_exam_co_attainment(inp)

        # Check CO2 calculations
        co2_res = result.students[0].co_results["CO2"]
        self.assertAlmostEqual(co2_res.co_max_marks, 34.0)
        self.assertAlmostEqual(co2_res.obtained_marks, 29.0)
        expected_co2_pct = (29.0 / 34.0) * 100.0
        self.assertAlmostEqual(co2_res.co_percentage, expected_co2_pct)
        # Expected percentage ~ 85.29% > 55.0% -> attainment MUST be 1
        self.assertEqual(co2_res.attainment, 1)

        # Check CO3 calculations
        co3_res = result.students[0].co_results["CO3"]
        self.assertAlmostEqual(co3_res.co_max_marks, 16.0)
        self.assertAlmostEqual(co3_res.obtained_marks, 6.0)
        expected_co3_pct = (6.0 / 16.0) * 100.0
        self.assertAlmostEqual(co3_res.co_percentage, expected_co3_pct)
        # Expected percentage = 37.5% < 55.0% -> attainment MUST be 0
        self.assertEqual(co3_res.attainment, 0)

        # Ensure return types are strictly numeric int (1 or 0), not string or boolean
        self.assertIsInstance(co2_res.attainment, int)
        self.assertIsInstance(co3_res.attainment, int)
        self.assertNotIsInstance(co2_res.attainment, bool)
        self.assertNotIsInstance(co3_res.attainment, bool)

    def test_overall_attainment_thresholds_follow_workbook_levels(self):
        """Workbook-aligned overall CO attainment bands: 55%+ below 60 is Level 1, 60%+ below 65 is Level 2, >65 is Level 3, and 65% is unresolved."""
        questions = [
            Question(question_number="1", max_marks=10.0, mapped_co="CO1"),
            Question(question_number="2", max_marks=10.0, mapped_co="CO1"),
        ]

        # Use 100 students so each requested cohort percentage is exactly representable.
        def build_input(attaining_students):
            return ExamCalculationInput(
                exam_id="EXAM_OVERALL",
                pass_percentage=55.0,
                covered_cos=["CO1"],
                questions=questions,
                students=[Student(register_no=f"S{i:03d}", name=f"Student {i}") for i in range(100)],
                marks=[
                    mark
                    for i in range(100)
                    for mark in (
                        StudentQuestionMark(
                            register_no=f"S{i:03d}",
                            question_number="1",
                            obtained_mark=10.0 if i < attaining_students else 0.0,
                        ),
                        StudentQuestionMark(
                            register_no=f"S{i:03d}",
                            question_number="2",
                            obtained_mark=1.0 if i < attaining_students else 0.0,
                        ),
                    )
                ],
            )

        result_55 = calculate_exam_co_attainment(build_input(55))
        self.assertEqual(result_55.overall_co_attainment["CO1"].attainment_level, 1)

        result_60 = calculate_exam_co_attainment(build_input(60))
        self.assertEqual(result_60.overall_co_attainment["CO1"].attainment_level, 2)

        result_64 = calculate_exam_co_attainment(build_input(64))
        self.assertEqual(result_64.overall_co_attainment["CO1"].attainment_level, 2)

        result_65 = calculate_exam_co_attainment(build_input(65))
        self.assertIsNone(result_65.overall_co_attainment["CO1"].attainment_level)

        result_70 = calculate_exam_co_attainment(build_input(70))
        self.assertEqual(result_70.overall_co_attainment["CO1"].attainment_level, 3)

    # 21. Model exam pattern covering all 5 Course Outcomes (CO1 to CO5)
    def test_model_exam_pattern_five_cos(self):
        # 10 Part A questions (2 marks each, 2 per CO) + 5 Part B questions (8 marks each, 1 per CO) = 60 marks total
        questions = []
        for i in range(1, 11):
            co_num = ((i - 1) // 2) + 1
            questions.append(Question(question_number=str(i), max_marks=2.0, mapped_co=f"CO{co_num}"))
        for j in range(11, 16):
            co_num = j - 10
            questions.append(Question(question_number=str(j), max_marks=8.0, mapped_co=f"CO{co_num}"))

        # Max marks per CO = 2*2 + 8 = 12 marks each
        student = Student(register_no="TEST-REG-0001", name="Sample Student 1")
        # CO1: Q1=2, Q2=2, Q11=8 -> 12/12 = 100% (>55% -> 1)
        # CO2: Q3=2, Q4=1, Q12=4 -> 7/12 = 58.33% (>55% -> 1)
        # CO3: Q5=1, Q6=1, Q13=4 -> 6/12 = 50.0% (<=55% -> 0)
        # CO4: Q7=0, Q8=0, Q14=0 -> 0/12 = 0.0% (<=55% -> 0)
        # CO5: Q9=2, Q10=1.5, Q15=6 -> 9.5/12 = 79.17% (>55% -> 1)
        marks = [
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=2.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="2", obtained_mark=2.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="3", obtained_mark=2.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="4", obtained_mark=1.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="5", obtained_mark=1.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="6", obtained_mark=1.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="7", obtained_mark=0.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="8", obtained_mark=0.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="9", obtained_mark=2.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="10", obtained_mark=1.5),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="11", obtained_mark=8.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="12", obtained_mark=4.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="13", obtained_mark=4.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="14", obtained_mark=0.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="15", obtained_mark=6.0),
        ]
        inp = ExamCalculationInput(
            exam_id="MODEL_EXAM",
            pass_percentage=55.0,
            covered_cos=["CO1", "CO2", "CO3", "CO4", "CO5"],
            questions=questions,
            students=[student],
            marks=marks,
        )
        res = calculate_exam_co_attainment(inp)
        self.assertEqual(len(res.covered_cos), 5)
        for co in ["CO1", "CO2", "CO3", "CO4", "CO5"]:
            self.assertAlmostEqual(res.co_max_marks[co], 12.0)

        s_res = res.students[0]
        self.assertEqual(s_res.co_results["CO1"].attainment, 1)
        self.assertEqual(s_res.co_results["CO2"].attainment, 1)
        self.assertEqual(s_res.co_results["CO3"].attainment, 0)
        self.assertEqual(s_res.co_results["CO4"].attainment, 0)
        self.assertEqual(s_res.co_results["CO5"].attainment, 1)

    # 22. Zero marks on all questions produces 0% and attainment 0
    def test_zero_marks_produces_zero_percent_and_zero_attainment(self):
        questions = [Question(question_number="1", max_marks=10.0, mapped_co="CO1")]
        students = [self.default_student]
        marks = [StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=0.0)]
        inp = ExamCalculationInput(
            exam_id="EXAM_ZERO_MARKS",
            pass_percentage=55.0,
            covered_cos=["CO1"],
            questions=questions,
            students=students,
            marks=marks,
        )
        res = calculate_exam_co_attainment(inp)
        co1 = res.students[0].co_results["CO1"]
        self.assertAlmostEqual(co1.obtained_marks, 0.0)
        self.assertAlmostEqual(co1.co_percentage, 0.0)
        self.assertEqual(co1.attainment, 0)

    # 23. Duplicate student register number rejected
    def test_duplicate_student_register_number_rejected(self):
        questions = [Question(question_number="1", max_marks=10.0, mapped_co="CO1")]
        students = [
            Student(register_no="TEST-REG-0001", name="Sample Student 1"),
            Student(register_no="TEST-REG-0001", name="Sample Student 2"),
        ]
        marks = [StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=5.0)]
        inp = ExamCalculationInput(
            exam_id="EXAM_DUP_STUDENT",
            pass_percentage=55.0,
            covered_cos=["CO1"],
            questions=questions,
            students=students,
            marks=marks,
        )
        with self.assertRaises(DomainValidationError):
            calculate_exam_co_attainment(inp)

    # 24. Mark referencing unknown student rejected
    def test_mark_referencing_unknown_student_rejected(self):
        questions = [Question(question_number="1", max_marks=10.0, mapped_co="CO1")]
        students = [self.default_student]
        marks = [StudentQuestionMark(register_no="NON_EXISTENT", question_number="1", obtained_mark=5.0)]
        inp = ExamCalculationInput(
            exam_id="EXAM_UNKNOWN_STUDENT",
            pass_percentage=55.0,
            covered_cos=["CO1"],
            questions=questions,
            students=students,
            marks=marks,
        )
        with self.assertRaises(DomainValidationError):
            calculate_exam_co_attainment(inp)

    # 25. Mark referencing unknown question rejected
    def test_mark_referencing_unknown_question_rejected(self):
        questions = [Question(question_number="1", max_marks=10.0, mapped_co="CO1")]
        students = [self.default_student]
        marks = [StudentQuestionMark(register_no="TEST-REG-0001", question_number="Q999", obtained_mark=5.0)]
        inp = ExamCalculationInput(
            exam_id="EXAM_UNKNOWN_QUESTION",
            pass_percentage=55.0,
            covered_cos=["CO1"],
            questions=questions,
            students=students,
            marks=marks,
        )
        with self.assertRaises(DomainValidationError):
            calculate_exam_co_attainment(inp)

    # 26. Duplicate mark entry for same student and question rejected
    def test_duplicate_mark_entry_rejected(self):
        questions = [Question(question_number="1", max_marks=10.0, mapped_co="CO1")]
        students = [self.default_student]
        marks = [
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=5.0),
            StudentQuestionMark(register_no="TEST-REG-0001", question_number="1", obtained_mark=6.0),
        ]
        inp = ExamCalculationInput(
            exam_id="EXAM_DUP_MARK",
            pass_percentage=55.0,
            covered_cos=["CO1"],
            questions=questions,
            students=students,
            marks=marks,
        )
        with self.assertRaises(DomainValidationError):
            calculate_exam_co_attainment(inp)


if __name__ == "__main__":
    unittest.main()
