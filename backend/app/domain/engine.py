"""
Authoritative CO calculation engine.
Deterministic, pure domain calculation logic.
Zero dependencies on database, HTTP, UI, or export frameworks.
"""

from decimal import Decimal
from typing import Dict, List, Set, Tuple
from app.domain.attainment_levels import classify_attainment_level
from app.domain.models import (
    ExamCalculationInput,
    CanonicalExamResult,
    StudentExamResult,
    StudentCOResult,
    Question,
    OverallCOAttainment,
)
from app.domain.errors import (
    InvalidExamConfigurationError,
    InvalidQuestionConfigurationError,
    InvalidMarkError,
    IncompleteDataError,
    DomainValidationError,
)


def validate_calculation_input(input_data: ExamCalculationInput, require_complete_marks: bool = True) -> None:
    """
    Validates the entire calculation input payload against all confirmed domain rules.
    Raises domain-specific exceptions on any violation.
    """
    # 1. Pass Percentage Validation
    if not isinstance(input_data.pass_percentage, (int, float)):
        raise InvalidExamConfigurationError("Pass percentage must be a valid number.")
    if input_data.pass_percentage <= 0.0 or input_data.pass_percentage > 100.0:
        raise InvalidExamConfigurationError(
            f"Pass percentage must be > 0.0 and <= 100.0, got: {input_data.pass_percentage}"
        )

    # 2. Covered COs Validation
    if not input_data.covered_cos:
        raise InvalidExamConfigurationError("Exam must have at least one explicitly covered CO.")

    seen_cos: Set[str] = set()
    for co in input_data.covered_cos:
        if not co or not isinstance(co, str) or not co.strip():
            raise InvalidExamConfigurationError("Covered CO code cannot be empty.")
        co_clean = co.strip()
        if co_clean in seen_cos:
            raise InvalidExamConfigurationError(f"Duplicate covered CO: '{co_clean}'.")
        seen_cos.add(co_clean)

    # 3. Questions Validation
    if not input_data.questions:
        raise InvalidQuestionConfigurationError("Exam must have at least one configured question.")

    seen_q_nums: Set[str] = set()
    co_totals: Dict[str, float] = {co.strip(): 0.0 for co in input_data.covered_cos}

    for q in input_data.questions:
        if not q.question_number or not str(q.question_number).strip():
            raise InvalidQuestionConfigurationError("Question number cannot be empty.")
        q_num = str(q.question_number).strip()
        if q_num in seen_q_nums:
            raise InvalidQuestionConfigurationError(f"Duplicate question number '{q_num}' in exam configuration.")
        seen_q_nums.add(q_num)

        if not isinstance(q.max_marks, (int, float)) or q.max_marks <= 0.0:
            raise InvalidQuestionConfigurationError(
                f"Question '{q_num}' maximum marks must be strictly positive, got: {q.max_marks}"
            )

        if not q.mapped_co or not str(q.mapped_co).strip():
            raise InvalidQuestionConfigurationError(f"Question '{q_num}' must have an assigned CO mapping.")
        mapped_co_clean = str(q.mapped_co).strip()

        if mapped_co_clean not in co_totals:
            raise InvalidQuestionConfigurationError(
                f"Question '{q_num}' is mapped to CO '{mapped_co_clean}', which is not among the exam's covered COs: {list(co_totals.keys())}."
            )

        co_totals[mapped_co_clean] += float(q.max_marks)

    # 4. Covered CO Maximum Marks Validation
    for co, total_max in co_totals.items():
        if total_max <= 0.0:
            raise InvalidExamConfigurationError(
                f"Covered CO '{co}' has zero maximum marks. Every covered CO must have at least one mapped question."
            )

    # 5. Students Validation
    seen_student_regs: Set[str] = set()
    for s in input_data.students:
        if not s.register_no or not str(s.register_no).strip():
            raise DomainValidationError("Student register number cannot be empty.")
        reg_clean = str(s.register_no).strip()
        if reg_clean in seen_student_regs:
            raise DomainValidationError(f"Duplicate student register number '{reg_clean}'.")
        seen_student_regs.add(reg_clean)

    # 6. Marks Validation
    q_max_map: Dict[str, float] = {str(q.question_number).strip(): float(q.max_marks) for q in input_data.questions}
    seen_mark_pairs: Set[Tuple[str, str]] = set()

    # Track entered marks per student for completeness checking
    student_entered_questions: Dict[str, Set[str]] = {s.register_no.strip(): set() for s in input_data.students}

    for m in input_data.marks:
        m_reg = str(m.register_no).strip()
        m_q = str(m.question_number).strip()

        if m_reg not in seen_student_regs:
            raise DomainValidationError(f"Mark references unknown student register number: '{m_reg}'.")

        if m_q not in q_max_map:
            raise DomainValidationError(f"Mark references unknown question number: '{m_q}'.")

        pair = (m_reg, m_q)
        if pair in seen_mark_pairs:
            raise DomainValidationError(f"Duplicate mark entry for student '{m_reg}' on question '{m_q}'.")
        seen_mark_pairs.add(pair)

        if not isinstance(m.obtained_mark, (int, float)):
            raise InvalidMarkError(f"Mark for student '{m_reg}' on question '{m_q}' must be numeric.")

        obtained = float(m.obtained_mark)
        if obtained < 0.0:
            raise InvalidMarkError(
                f"Mark cannot be negative: got {obtained} for student '{m_reg}' on question '{m_q}'."
            )

        max_allowed = q_max_map[m_q]
        if obtained > max_allowed:
            raise InvalidMarkError(
                f"Obtained mark {obtained} exceeds question '{m_q}' maximum marks {max_allowed} for student '{m_reg}'."
            )

        student_entered_questions[m_reg].add(m_q)

    # 7. Incomplete Data Handling (Does not guess an absence policy or blank-as-zero)
    if require_complete_marks and input_data.students and input_data.questions:
        all_q_set = set(q_max_map.keys())
        for reg, entered_qs in student_entered_questions.items():
            missing_qs = all_q_set - entered_qs
            if missing_qs:
                sorted_missing = sorted(list(missing_qs))
                raise IncompleteDataError(
                    f"Student '{reg}' has no mark recorded for question(s): {', '.join(sorted_missing)}. "
                    "Unresolved mark policy: Incomplete data is rejected rather than silently guessing an unapproved academic rule."
                )


def calculate_exam_co_attainment(
    input_data: ExamCalculationInput,
    require_complete_marks: bool = True
) -> CanonicalExamResult:
    """
    Authoritative CO attainment calculation function.
    
    Mathematical rules:
      1. CO Maximum Marks = Sum of max_marks of all questions mapped to that CO.
      2. Student CO Obtained Marks = Sum of obtained marks for all questions mapped to that CO.
      3. CO Percentage = (Student CO Marks / CO Maximum Marks) * 100.
    4. Student CO Attainment = 1 if CO Percentage >= Pass Percentage else 0.
      5. Overall CO attainment level is classified by cohort percentage using the workbook bands:
         - 55% <= pct < 60% => Level 1
         - 60% <= pct < 65% => Level 2
         - pct > 65% => Level 3
         - pct == 65% is left unresolved by the workbook wording and returned as None.

    Returns a CanonicalExamResult consumed by UI and report generators.
    """
    # Run full domain validation
    validate_calculation_input(input_data, require_complete_marks=require_complete_marks)

    clean_covered_cos: List[str] = [co.strip() for co in input_data.covered_cos]

    # Map question_number -> Question
    question_map: Dict[str, Question] = {
        str(q.question_number).strip(): q for q in input_data.questions
    }

    # 1. Compute CO Maximum Marks
    co_max_marks: Dict[str, float] = {co: 0.0 for co in clean_covered_cos}
    for q in input_data.questions:
        co = str(q.mapped_co).strip()
        co_max_marks[co] += float(q.max_marks)

    # Map (register_no, question_number) -> obtained_mark
    marks_lookup: Dict[Tuple[str, str], float] = {
        (str(m.register_no).strip(), str(m.question_number).strip()): float(m.obtained_mark)
        for m in input_data.marks
    }

    student_results: List[StudentExamResult] = []

    # 2. Compute for each student
    for s in input_data.students:
        s_reg = str(s.register_no).strip()
        s_name = str(s.name).strip()

        student_q_marks: Dict[str, float] = {}
        total_obtained = 0.0

        co_obtained_marks: Dict[str, float] = {co: 0.0 for co in clean_covered_cos}

        for q in input_data.questions:
            q_num = str(q.question_number).strip()
            obtained = marks_lookup.get((s_reg, q_num), 0.0)
            student_q_marks[q_num] = obtained
            total_obtained += obtained
            co_obtained_marks[str(q.mapped_co).strip()] += obtained

        # Calculate CO results for this student
        co_results: Dict[str, StudentCOResult] = {}
        for co in clean_covered_cos:
            max_m = co_max_marks[co]
            obt_m = co_obtained_marks[co]

            # Percentage: (Obtained / Max) * 100
            # Calculated with Decimal for exact base-10 arithmetic without IEEE-754 binary float artifacts
            obt_dec = Decimal(str(obt_m))
            max_dec = Decimal(str(max_m))
            pct_dec = (obt_dec / max_dec) * Decimal(100)
            percentage = float(pct_dec)

            # The workbook threshold is inclusive: reaching the configured percentage attains the CO.
            pass_pct_dec = Decimal(str(input_data.pass_percentage))
            attainment: int = 1 if pct_dec >= pass_pct_dec else 0

            co_results[co] = StudentCOResult(
                co_code=co,
                co_max_marks=max_m,
                obtained_marks=obt_m,
                co_percentage=percentage,
                attainment=attainment,
            )

        student_results.append(
            StudentExamResult(
                register_no=s_reg,
                name=s_name,
                question_marks=student_q_marks,
                total_obtained=total_obtained,
                co_results=co_results,
            )
        )

    overall_co_attainment: Dict[str, OverallCOAttainment] = {}
    total_students = len(student_results)
    for co in clean_covered_cos:
        students_attaining = sum(1 for s in student_results if s.co_results[co].attainment == 1)
        attainment_pct = (students_attaining / total_students) * 100.0 if total_students else 0.0
        attainment_level = classify_attainment_level(attainment_pct)

        overall_co_attainment[co] = OverallCOAttainment(
            co_code=co,
            total_students=total_students,
            students_attaining_co=students_attaining,
            attainment_percentage=float(attainment_pct),
            attainment_level=attainment_level,
        )

    return CanonicalExamResult(
        exam_id=input_data.exam_id,
        pass_percentage=float(input_data.pass_percentage),
        covered_cos=clean_covered_cos,
        co_max_marks=co_max_marks,
        students=student_results,
        overall_co_attainment=overall_co_attainment,
    )
