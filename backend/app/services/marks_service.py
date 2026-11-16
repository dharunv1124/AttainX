"""
FastAPI Application Marks Service for Phase 6.
Directly connects FastAPI and PostgreSQL/SQLite database to the pure Phase 3 domain calculation engine.
Zero subprocesses, zero CLI bridges. Single Source of Truth architecture.
"""

from datetime import datetime, time
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, status
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.db.models import Exam, Section, Student, StudentAcademicPlacement, StudentMark
from app.repositories.exam_repository import ExamRepository
from app.repositories.marks_repository import MarksRepository
from app.repositories.student_repository import StudentRepository
from app.domain.marks_service import (
    calculate_exam_co_statistics,
    validate_student_cohort,
    validate_and_format_marks,
    process_exam_marks_and_calculate,
    CohortConsistencyError,
    MarksServiceError,
)
from app.domain.errors import InvalidMarkError, IncompleteDataError, DomainValidationError


class MarksApiService:
    def __init__(self, db: Session):
        self.db = db
        self.exam_repo = ExamRepository(db)
        self.marks_repo = MarksRepository(db)

    def _get_exam_or_404(self, exam_id: int) -> Exam:
        exam = self.exam_repo.get(exam_id)
        if not exam:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Exam with ID {exam_id} not found",
            )
        return exam

    def get_exam_roster(self, exam_id: int) -> List[Dict[str, Any]]:
        """
        1. Load the students belonging to the exam's selected Department -> Year -> Semester -> Section.
        """
        exam = self._get_exam_or_404(exam_id)
        cohort_section = aliased(Section)
        cohort_assignment = select(cohort_section.id).where(
            cohort_section.id == Student.section_id,
            cohort_section.batch_id == exam.batch_id,
            cohort_section.department_id == exam.department_id,
            cohort_section.name == exam.section.name,
        ).correlate(Student)
        section_placements = select(StudentAcademicPlacement.id).where(
            StudentAcademicPlacement.student_id == Student.id,
            StudentAcademicPlacement.batch_id == exam.batch_id,
            StudentAcademicPlacement.section_id == exam.section_id,
        ).correlate(Student)
        dated_placements = section_placements
        if exam.exam_date is not None:
            exam_end = datetime.combine(exam.exam_date, time.max)
            dated_placements = dated_placements.where(
                StudentAcademicPlacement.effective_from <= exam_end,
                or_(
                    StudentAcademicPlacement.effective_to.is_(None),
                    func.date(StudentAcademicPlacement.effective_to) >= exam.exam_date,
                ),
            )
        marked_student_with_exam_placement = exists(select(StudentMark.id).where(
            StudentMark.student_id == Student.id,
            StudentMark.exam_id == exam.id,
            exists(section_placements),
        )).correlate(Student)
        students_query = self.db.query(Student).filter(
            Student.batch_id == exam.batch_id,
            Student.archived_at.is_(None),
            or_(
                exists(cohort_assignment),
                exists(dated_placements),
                marked_student_with_exam_placement,
            ),
        )
        students = sorted(students_query.all(), key=StudentRepository._natural_register_key)
        return [
            {
                "id": s.id,
                "register_no": s.register_no,
                "name": s.name,
                "section_id": exam.section_id,
            }
            for s in students
        ]

    def get_exam_questions(self, exam_id: int) -> List[Dict[str, Any]]:
        """
        2. Load the questions configured for that exam in question-number order.
        """
        exam = self._get_exam_or_404(exam_id)
        questions = exam.questions or []

        q_list = []
        for q in questions:
            if hasattr(q, "question_number"):
                q_list.append({
                    "id": getattr(q, "id", None),
                    "question_number": q.question_number,
                    "max_marks": float(q.max_marks),
                    "co_code": q.co_code,
                })
            elif isinstance(q, dict):
                q_list.append({
                    "id": q.get("id"),
                    "question_number": q.get("question_number"),
                    "max_marks": float(q.get("max_marks", 0.0)),
                    "co_code": q.get("co_code"),
                })

        def sort_key(item):
            q_num = str(item.get("question_number", ""))
            digits = "".join(filter(str.isdigit, q_num))
            return int(digits) if digits else 9999

        sorted_questions = sorted(q_list, key=sort_key)
        return sorted_questions

    def _canonicalize_question_references(
        self,
        questions: List[Dict[str, Any]],
        submitted_marks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Resolve submitted IDs to the exact configured question records."""
        questions_by_id = {int(q["id"]): q for q in questions if q.get("id") is not None}
        canonical_marks = []

        for mark in submitted_marks:
            question_id = mark.get("question_id")
            question_number = mark.get("question_number")
            question = None

            if question_id is not None:
                try:
                    question = questions_by_id.get(int(question_id))
                except (TypeError, ValueError):
                    question = None
                if question is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Question ID '{question_id}' is not configured for this exam.",
                    )
                if question_number and str(question_number).strip() != str(question["question_number"]).strip():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Question ID '{question_id}' does not match question number "
                            f"'{question_number}'."
                        ),
                    )
            else:
                question = next(
                    (q for q in questions if str(q["question_number"]).strip() == str(question_number).strip()),
                    None,
                )
                if question is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Mark references unknown question '{question_number}'.",
                    )

            canonical_marks.append({
                **mark,
                "question_id": question["id"],
                "question_number": question["question_number"],
            })

        return canonical_marks

    def get_saved_marks_and_results(self, exam_id: int) -> Dict[str, Any]:
        """
        Load saved marks and calculated CO results for an exam.
        Recalculates CO results using the authoritative Phase 3 Python domain engine.
        """
        exam = self._get_exam_or_404(exam_id)
        saved_marks = self.marks_repo.get_by_exam(exam_id)
        questions = self.get_exam_questions(exam_id)
        questions_by_number = {q["question_number"]: q for q in questions}

        marks_list = [
            {
            "question_id": questions_by_number[sm.question_number]["id"],
                "register_no": sm.student.register_no,
                "question_number": sm.question_number,
                "obtained_mark": sm.obtained_mark,
            }
            for sm in saved_marks
            if sm.student
        ]

        enrolled_students = self.get_exam_roster(exam_id)
        question_co_statistics = calculate_exam_co_statistics(questions, enrolled_students, marks_list)

        if not marks_list:
            return {
                "exam_id": exam_id,
                "marks": [],
                "calculation_result": None,
                "question_co_statistics": question_co_statistics,
            }

        co_codes = [c.co_code if hasattr(c, "co_code") else str(c) for c in (exam.covered_cos or [])]

        try:
            domain_result = process_exam_marks_and_calculate(
                exam_id=exam.id,
                pass_percentage=float(exam.pass_percentage),
                covered_cos=co_codes,
                questions=questions,
                enrolled_students=enrolled_students,
                submitted_marks=marks_list,
                require_complete=False,
            )
            calc_dict = {
                "exam_id": domain_result.exam_id,
                "pass_percentage": domain_result.pass_percentage,
                "covered_cos": domain_result.covered_cos,
                "co_max_marks": domain_result.co_max_marks,
                "students": [
                    {
                        "register_no": s.register_no,
                        "name": s.name,
                        "question_marks": s.question_marks,
                        "total_obtained": s.total_obtained,
                        "co_results": {
                            co_code: {
                                "co_code": co_res.co_code,
                                "co_max_marks": co_res.co_max_marks,
                                "obtained_marks": co_res.obtained_marks,
                                "co_percentage": co_res.co_percentage,
                                "attainment": co_res.attainment,
                            }
                            for co_code, co_res in s.co_results.items()
                        },
                    }
                    for s in domain_result.students
                ],
                "overall_co_attainment": {
                    co: {
                        "co_code": summary.co_code,
                        "total_students": summary.total_students,
                        "students_attaining_co": summary.students_attaining_co,
                        "attainment_percentage": summary.attainment_percentage,
                        "attainment_level": summary.attainment_level,
                    }
                    for co, summary in domain_result.overall_co_attainment.items()
                },
            }
        except Exception:
            calc_dict = None

        return {
            "exam_id": exam_id,
            "marks": marks_list,
            "calculation_result": calc_dict,
            "question_co_statistics": question_co_statistics,
        }

    def save_marks_and_calculate(
        self,
        exam_id: int,
        submitted_marks: List[Dict[str, Any]],
        require_complete: bool = False,
    ) -> Dict[str, Any]:
        """
        Validates cohort consistency, validates mark bounds, persists marks,
        and directly recalculates CO attainment using the Phase 3 domain engine.
        """
        exam = self._get_exam_or_404(exam_id)
        enrolled_students = self.get_exam_roster(exam_id)
        questions = self.get_exam_questions(exam_id)
        submitted_marks = self._canonicalize_question_references(questions, submitted_marks)

        student_by_reg = {
            s["register_no"].strip().upper(): s["id"]
            for s in enrolled_students
        }

        # 1. DATA CONSISTENCY & MARK BOUND VALIDATION (Phase 6 Rules)
        try:
            # Domain cohort check (rejects any student outside the exam's section)
            validate_student_cohort(enrolled_students, submitted_marks)
            # Domain mark validation (numeric, non-negative, <= question maximum)
            validated_marks = validate_and_format_marks(questions, submitted_marks)
        except CohortConsistencyError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        except InvalidMarkError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        except (DomainValidationError, MarksServiceError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

        # 2. PERSISTENCE IN REPOSITORY
        for m in validated_marks:
            reg_clean = m.register_no.strip().upper()
            student_id = student_by_reg[reg_clean]
            self.marks_repo.upsert_student_mark(
                exam_id=exam_id,
                student_id=student_id,
                question_number=m.question_number,
                obtained_mark=float(m.obtained_mark),
            )

        saved_marks = self.marks_repo.get_by_exam(exam_id)
        question_co_statistics = calculate_exam_co_statistics(
            questions,
            enrolled_students,
            [
                {
                    "register_no": mark.student.register_no,
                    "question_number": mark.question_number,
                    "obtained_mark": mark.obtained_mark,
                }
                for mark in saved_marks
                if mark.student
            ],
        )

        # 3. DIRECT PHASE 3 ENGINE CALCULATION (Zero subprocess, Single Source of Truth)
        co_codes = [c.co_code if hasattr(c, "co_code") else str(c) for c in (exam.covered_cos or [])]
        try:
            domain_result = process_exam_marks_and_calculate(
                exam_id=exam.id,
                pass_percentage=float(exam.pass_percentage),
                covered_cos=co_codes,
                questions=questions,
                enrolled_students=enrolled_students,
                submitted_marks=[
                    {
                        "register_no": m.register_no,
                        "question_number": m.question_number,
                        "obtained_mark": m.obtained_mark,
                    }
                    for m in validated_marks
                ],
                require_complete=require_complete,
            )
        except IncompleteDataError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CO calculation failed in Phase 3 domain engine: {str(e)}",
            )

        calc_dict = {
            "exam_id": domain_result.exam_id,
            "pass_percentage": domain_result.pass_percentage,
            "covered_cos": domain_result.covered_cos,
            "co_max_marks": domain_result.co_max_marks,
            "students": [
                {
                    "register_no": s.register_no,
                    "name": s.name,
                    "question_marks": s.question_marks,
                    "total_obtained": s.total_obtained,
                    "co_results": {
                        co_code: {
                            "co_code": co_res.co_code,
                            "co_max_marks": co_res.co_max_marks,
                            "obtained_marks": co_res.obtained_marks,
                            "co_percentage": co_res.co_percentage,
                            "attainment": co_res.attainment,
                        }
                        for co_code, co_res in s.co_results.items()
                    },
                }
                for s in domain_result.students
            ],
            "overall_co_attainment": {
                co: {
                    "co_code": summary.co_code,
                    "total_students": summary.total_students,
                    "students_attaining_co": summary.students_attaining_co,
                    "attainment_percentage": summary.attainment_percentage,
                    "attainment_level": summary.attainment_level,
                }
                for co, summary in domain_result.overall_co_attainment.items()
            },
        }

        return {
            "success": True,
            "exam_id": exam_id,
            "marks": [
                {
                    "register_no": m.register_no,
                    "question_number": m.question_number,
                    "obtained_mark": m.obtained_mark,
                }
                for m in validated_marks
            ],
            "calculation_result": calc_dict,
            "question_co_statistics": question_co_statistics,
        }
