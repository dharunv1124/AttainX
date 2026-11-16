"""
Phase 6 Domain Marks Service.
Orchestrates:
- Student roster validation (cohort consistency)
- Mark validation (numeric, non-negative, <= question maximum, no silent clamping)
- Missing mark policy enforcement (Phase 3 compliance)
- Deterministic CO attainment calculation via the Phase 3 engine (Single Source of Truth)
- Pure domain logic with zero UI or framework dependencies.
"""

from decimal import Decimal
from typing import Dict, List, Any, Optional
from app.domain.models import (
    Question,
    Student,
    StudentQuestionMark,
    ExamCalculationInput,
    CanonicalExamResult,
)
from app.domain.engine import calculate_exam_co_attainment
from app.domain.errors import (
    DomainValidationError,
    InvalidMarkError,
    IncompleteDataError,
)


class MarksServiceError(DomainValidationError):
    """Base error for marks service validation failures."""
    pass


class CohortConsistencyError(MarksServiceError):
    """Raised when a mark references a student outside the exam's enrolled cohort."""
    pass


def calculate_exam_co_statistics(
    questions: List[Dict[str, Any]],
    enrolled_students: List[Dict[str, Any]],
    submitted_marks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Calculate question-level 50% statistics and averages grouped by mapped CO."""
    student_regs = {
        str(student.get("register_no", student.get("registerNo", ""))).strip().upper()
        for student in enrolled_students
    }
    marks_by_student_question: Dict[tuple[str, str], Decimal] = {}
    for mark in submitted_marks:
        register_no = str(mark.get("register_no", mark.get("registerNo", ""))).strip().upper()
        question_number = str(mark.get("question_number", mark.get("questionNumber", ""))).strip()
        raw_mark = mark.get("obtained_mark", mark.get("obtainedMark"))
        if (
            register_no not in student_regs
            or raw_mark is None
            or (isinstance(raw_mark, str) and not raw_mark.strip())
        ):
            continue
        marks_by_student_question[(register_no, question_number)] = Decimal(str(raw_mark))

    question_statistics = []
    co_percentages: Dict[str, List[Decimal]] = {}
    for question in questions:
        question_number = str(question.get("question_number", question.get("questionNumber", ""))).strip()
        co_code = str(question.get("mapped_co", question.get("co_code", question.get("coCode", "")))).strip().upper()
        max_marks = Decimal(str(question.get("max_marks", question.get("maxMarks", 0))))
        threshold = max_marks * Decimal("0.50")
        question_marks = [
            marks_by_student_question[(register_no, question_number)]
            for register_no in student_regs
            if (register_no, question_number) in marks_by_student_question
        ]
        attempted = len(question_marks)
        at_least_half = sum(1 for mark in question_marks if mark >= threshold)
        percentage = (
            Decimal(at_least_half) / Decimal(attempted) * Decimal(100)
            if attempted
            else None
        )
        if co_code:
            co_percentages.setdefault(co_code, [])
            if percentage is not None:
                co_percentages[co_code].append(percentage)
        question_statistics.append({
            "question_number": question_number,
            "co_code": co_code,
            "students_at_least_50_percent": at_least_half,
            "students_attempted": attempted,
            "percentage_at_least_50_percent": percentage,
        })

    co_averages = [
        {
            "co_code": co_code,
            "average_percentage": sum(percentages, Decimal(0)) / Decimal(len(percentages)) if percentages else None,
        }
        for co_code, percentages in co_percentages.items()
    ]
    return {"questions": question_statistics, "co_averages": co_averages}


def validate_student_cohort(
    enrolled_students: List[Dict[str, Any]],
    submitted_marks: List[Dict[str, Any]],
) -> None:
    """
    Verifies that every student in the submitted marks belongs to the exam's configured class/section cohort.
    Marks for students outside the cohort are strictly rejected.
    """
    enrolled_regs = {str(s.get("register_no", s.get("registerNo", ""))).strip() for s in enrolled_students}

    for m in submitted_marks:
        reg = str(m.get("register_no", m.get("registerNo", ""))).strip()
        if not reg:
            raise MarksServiceError("Student register number cannot be empty in marks entry.")
        if reg not in enrolled_regs:
            raise CohortConsistencyError(
                f"Student '{reg}' does not belong to the exam's configured class/section cohort. "
                "Marks for students outside the exam cohort are strictly rejected."
            )


def validate_and_format_marks(
    questions: List[Dict[str, Any]],
    submitted_marks: List[Dict[str, Any]],
) -> List[StudentQuestionMark]:
    """
    Validates mark entry for each question according to Phase 6 rules:
    - Must be numeric.
    - Must not be negative.
    - Must not exceed the question's maximum mark.
    - Rejects invalid marks without guessing or silent clamping.
    """
    q_map: Dict[str, float] = {}
    for q in questions:
        q_num = str(q.get("question_number", q.get("questionNumber", ""))).strip()
        max_m = float(q.get("max_marks", q.get("maxMarks", 0)))
        q_map[q_num] = max_m

    formatted_marks: List[StudentQuestionMark] = []

    for m in submitted_marks:
        reg = str(m.get("register_no", m.get("registerNo", ""))).strip()
        q_num = str(m.get("question_number", m.get("questionNumber", ""))).strip()

        if q_num not in q_map:
            raise MarksServiceError(f"Mark references unknown question '{q_num}'.")

        raw_val = m.get("obtained_mark", m.get("obtainedMark"))
        if raw_val is None or raw_val == "":
            continue  # Blank marks are not submitted

        # Check numeric
        try:
            val = float(raw_val)
        except (ValueError, TypeError):
            raise InvalidMarkError(
                f"Mark for student '{reg}' on question '{q_num}' must be numeric, got: {raw_val!r}."
            )

        # Check negative
        if val < 0.0:
            raise InvalidMarkError(
                f"Mark cannot be negative: got {val} for student '{reg}' on question '{q_num}'. "
                "Negative marks are strictly rejected."
            )

        # Check exceed maximum
        max_allowed = q_map[q_num]
        if val > max_allowed:
            raise InvalidMarkError(
                f"Obtained mark {val} exceeds question '{q_num}' maximum marks {max_allowed} for student '{reg}'. "
                "Values exceeding maximum marks are strictly rejected without silent clamping."
            )

        formatted_marks.append(
            StudentQuestionMark(
                register_no=reg,
                question_number=q_num,
                obtained_mark=val,
            )
        )

    return formatted_marks


def process_exam_marks_and_calculate(
    exam_id: Any,
    pass_percentage: float,
    covered_cos: List[str],
    questions: List[Dict[str, Any]],
    enrolled_students: List[Dict[str, Any]],
    submitted_marks: List[Dict[str, Any]],
    require_complete: bool = True,
) -> CanonicalExamResult:
    """
    Core Phase 6 entrypoint:
    1. Validates cohort consistency
    2. Validates marks constraints (numeric, >= 0, <= max)
    3. Calls Phase 3 authoritative CO calculation engine
    4. Returns CanonicalExamResult
    """
    # 1. Cohort check
    validate_student_cohort(enrolled_students, submitted_marks)

    # 2. Mark validation
    domain_marks = validate_and_format_marks(questions, submitted_marks)

    # 3. Build domain inputs
    domain_questions = [
        Question(
            question_number=str(q.get("question_number", q.get("questionNumber", ""))).strip(),
            max_marks=float(q.get("max_marks", q.get("maxMarks", 0))),
            mapped_co=str(q.get("mapped_co", q.get("co_code", q.get("coCode", "")))).strip().upper(),
        )
        for q in questions
    ]

    domain_students = [
        Student(
            register_no=str(s.get("register_no", s.get("registerNo", ""))).strip(),
            name=str(s.get("name", "")).strip(),
        )
        for s in enrolled_students
    ]

    calc_input = ExamCalculationInput(
        exam_id=exam_id,
        pass_percentage=float(pass_percentage),
        covered_cos=[c.strip().upper() for c in covered_cos],
        questions=domain_questions,
        students=domain_students,
        marks=domain_marks,
    )

    # 4. Phase 3 authoritative engine call
    return calculate_exam_co_attainment(calc_input, require_complete_marks=require_complete)
