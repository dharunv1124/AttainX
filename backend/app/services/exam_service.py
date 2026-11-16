"""
Exam Service implementing the Phase 5 Exam Workspace and Configuration workflow.
Enforces all validation rules strictly on the backend:
- Class context (Department -> Year -> Semester -> Section)
- Subject association
- Covered CO selection (authoritative, never inferred)
- Pass percentage validation
- Question configuration and Question-to-CO mapping validation
- Exam pattern validation for Internal 1, Internal 2, and Model exams
"""

from typing import List, Optional
from decimal import Decimal
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import Exam, Section, Subject, StudentAcademicPlacement
from app.repositories.exam_repository import ExamRepository
from app.repositories.department_repository import DepartmentRepository
from app.repositories.academic_repository import BatchRepository, YearRepository, SemesterRepository, SectionRepository
from app.repositories.subject_repository import SubjectRepository
from app.schemas.exam import ExamCreate, ExamUpdate, ExamQuestionConfig, ExamDetailRead


class ExamService:
    def __init__(self, db: Session):
        self.db = db
        self.batch_repo = BatchRepository(db)
        self.exam_repo = ExamRepository(db)
        self.dept_repo = DepartmentRepository(db)
        self.year_repo = YearRepository(db)
        self.sem_repo = SemesterRepository(db)
        self.section_repo = SectionRepository(db)
        self.subject_repo = SubjectRepository(db)

    def _validate_exam_payload(
        self,
        department_id: int,
        year_id: int,
        semester_id: int,
        section_id: int,
        subject_id: int,
        pass_percentage: float,
        covered_cos: List[str],
        questions: List[ExamQuestionConfig],
        exam_type: str = "CUSTOM",
        exam_name: Optional[str] = None,
        batch_id: Optional[int] = None,
        exclude_exam_id: Optional[int] = None,
    ) -> None:
        """Validate relational integrity and exam configuration rules."""
        # 1. Validate Master Data existence
        if not self.dept_repo.get(department_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
        if not self.year_repo.get_by_id(year_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Year not found")
        sem = self.sem_repo.get_by_id(semester_id)
        if not sem:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Semester not found")
        if sem.year_id != year_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected Semester does not belong to the selected Year",
            )
        section = self.section_repo.get_by_id(section_id)
        if not section:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
        if (
            section.department_id != department_id
            or section.year_id != year_id
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Section does not belong to the specified Department and Year",
            )
        if section.batch_id != batch_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Section does not belong to the selected Batch",
            )

        subject = self.subject_repo.get(subject_id)
        if not subject:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
        if subject.batch_id != batch_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subject does not belong to the selected Batch",
            )
        subject_scope = (subject.department_id, subject.year_id, subject.semester_id)
        exam_scope = (department_id, year_id, semester_id)
        if subject_scope != exam_scope and subject_scope != (None, None, None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subject does not belong to the specified Department, Year, and Semester",
            )

        # 2. Validate Pass Percentage
        if pass_percentage <= 0 or pass_percentage > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Pass percentage must be greater than 0 and at most 100. Received: {pass_percentage}",
            )

        # 3. Validate Covered COs
        clean_covered_cos = [c.strip().upper() for c in covered_cos if c.strip()]
        if not clean_covered_cos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Exam must have at least one covered Course Outcome (CO)",
            )
        if len(clean_covered_cos) != len(set(clean_covered_cos)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Duplicate Course Outcomes found in covered CO list",
            )

        # 4. Validate Questions
        if not questions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Exam must have at least one configured question",
            )

        seen_q_numbers = set()
        covered_cos_set = set(clean_covered_cos)
        mapped_cos = set()

        for q in questions:
            q_num = q.question_number.strip()
            if not q_num:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Question number cannot be empty",
                )
            if q_num.upper() in seen_q_numbers:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Duplicate question number '{q_num}' configured for this exam",
                )
            seen_q_numbers.add(q_num.upper())

            if q.max_marks <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Maximum marks for question '{q_num}' must be positive. Received: {q.max_marks}",
                )

            co = q.co_code.strip().upper()
            if not co:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Question '{q_num}' must be mapped to exactly one Course Outcome",
                )

            if co not in covered_cos_set:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Question '{q_num}' is mapped to '{co}', which is NOT in the exam's covered CO list {clean_covered_cos}",
                )
            mapped_cos.add(co)

        # 5. Every covered CO must have at least one mapped question
        unmapped_cos = covered_cos_set - mapped_cos
        if unmapped_cos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Every covered CO must have at least one mapped question. Unmapped COs: {sorted(list(unmapped_cos))}",
            )

        # 6. Validate confirmed exam pattern where applicable
        norm_type = exam_type.strip().upper()
        if norm_type in ("INTERNAL_1", "INTERNAL_2"):
            # Confirmed pattern: 10 x 2m + 3 x 10m = 50 marks (13 questions)
            total_marks = sum(q.max_marks for q in questions)
            if len(questions) != 13 or total_marks != 50.0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Pattern mismatch for {norm_type}: Confirmed pattern requires 13 questions "
                        f"(10 × 2-mark + 3 × 10-mark) totaling 50 marks. "
                        f"Provided: {len(questions)} questions totaling {total_marks} marks."
                    ),
                )
            two_mark_count = sum(1 for q in questions if q.max_marks == 2.0)
            ten_mark_count = sum(1 for q in questions if q.max_marks == 10.0)
            if two_mark_count != 10 or ten_mark_count != 3:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Pattern mismatch for {norm_type}: Question marks distribution must have "
                        f"10 questions of 2 marks and 3 questions of 10 marks."
                    ),
                )

        elif norm_type == "MODEL":
            # Confirmed pattern: 10 x 2m + 5 x 8m = 60 marks (15 questions)
            total_marks = sum(q.max_marks for q in questions)
            if len(questions) != 15 or total_marks != 60.0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Pattern mismatch for MODEL: Confirmed pattern requires 15 questions "
                        f"(10 × 2-mark + 5 × 8-mark) totaling 60 marks. "
                        f"Provided: {len(questions)} questions totaling {total_marks} marks."
                    ),
                )
            two_mark_count = sum(1 for q in questions if q.max_marks == 2.0)
            eight_mark_count = sum(1 for q in questions if q.max_marks == 8.0)
            if two_mark_count != 10 or eight_mark_count != 5:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Pattern mismatch for MODEL: Question marks distribution must have "
                        f"10 questions of 2 marks and 5 questions of 8 marks."
                    ),
                )

        if exam_name is not None and exam_name.strip():
            duplicate_exam = (
                self.db.query(Exam)
                .filter(
                    Exam.department_id == department_id,
                    Exam.year_id == year_id,
                    Exam.semester_id == semester_id,
                    Exam.section_id == section_id,
                    Exam.subject_id == subject_id,
                    Exam.batch_id == batch_id,
                    Exam.name.ilike(exam_name.strip()),
                )
                .filter(Exam.id != (exclude_exam_id or -1))
                .first()
            )
            if duplicate_exam:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"An exam named '{exam_name.strip()}' already exists for the selected "
                        "Department / Year / Semester / Section / Subject."
                    ),
                )

    def _format_exam_detail(self, exam: Exam) -> ExamDetailRead:
        student_count = self.db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.section_id == exam.section_id,
            StudentAcademicPlacement.batch_id == exam.batch_id,
            StudentAcademicPlacement.is_current.is_(True),
        ).count()
        total_marks = sum(float(q.max_marks) for q in exam.questions)
        return ExamDetailRead(
            id=exam.id,
            name=exam.name,
            exam_date=exam.exam_date,
            exam_type=exam.exam_type,
            batch_id=exam.batch_id,
            department_id=exam.department_id,
            year_id=exam.year_id,
            semester_id=exam.semester_id,
            section_id=exam.section_id,
            subject_id=exam.subject_id,
            pass_percentage=float(exam.pass_percentage),
            covered_cos=[c.co_code for c in exam.covered_cos],
            questions=[
                ExamQuestionConfig(
                    id=q.id,
                    question_number=q.question_number,
                    max_marks=float(q.max_marks),
                    co_code=q.co_code,
                )
                for q in exam.questions
            ],
            department_name=exam.department.name,
            department_code=exam.department.code,
            year_name=exam.year.name,
            semester_name=exam.semester.name,
            section_name=exam.section.name,
            subject_name=exam.subject.name,
            total_marks=total_marks,
            total_questions=len(exam.questions),
            student_count=student_count,
            created_at=exam.created_at,
            updated_at=exam.updated_at,
        )

    def create_exam(self, payload: ExamCreate) -> ExamDetailRead:
        # Validate all parameters and question configuration
        section = self.section_repo.get_by_id(payload.section_id)
        if section is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
        batch_id = payload.batch_id or section.batch_id
        if batch_id is None or batch_id != section.batch_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exam Batch does not match the selected section.")
        self._validate_exam_payload(
            department_id=payload.department_id,
            year_id=payload.year_id,
            semester_id=payload.semester_id,
            section_id=payload.section_id,
            subject_id=payload.subject_id,
            pass_percentage=payload.pass_percentage,
            covered_cos=payload.covered_cos,
            questions=payload.questions,
            exam_type=payload.exam_type,
            exam_name=payload.name,
            batch_id=batch_id,
        )

        clean_questions = [
            {
                "question_number": q.question_number.strip(),
                "max_marks": q.max_marks,
                "co_code": q.co_code.strip().upper(),
            }
            for q in payload.questions
        ]

        exam = self.exam_repo.create(
            name=payload.name,
            exam_type=payload.exam_type,
            batch_id=batch_id,
            department_id=payload.department_id,
            year_id=payload.year_id,
            semester_id=payload.semester_id,
            section_id=payload.section_id,
            subject_id=payload.subject_id,
            exam_date=payload.exam_date,
            pass_percentage=payload.pass_percentage,
            covered_cos=[c.strip().upper() for c in payload.covered_cos],
            questions=clean_questions,
        )
        return self._format_exam_detail(exam)

    def get_exam(self, exam_id: int) -> ExamDetailRead:
        exam = self.exam_repo.get_by_id_with_details(exam_id)
        if not exam:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
        return self._format_exam_detail(exam)

    def list_exams(
        self,
        department_id: Optional[int] = None,
        year_id: Optional[int] = None,
        semester_id: Optional[int] = None,
        section_id: Optional[int] = None,
        subject_id: Optional[int] = None,
        batch_id: Optional[int] = None,
    ) -> List[ExamDetailRead]:
        if batch_id is None:
            default_batch = self.batch_repo.get_default()
            if default_batch is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The default 2024–28 Batch is not configured or active.",
                )
            batch_id = default_batch.id
        exams = self.exam_repo.get_all_filtered(
            department_id=department_id,
            year_id=year_id,
            semester_id=semester_id,
            section_id=section_id,
            subject_id=subject_id,
            batch_id=batch_id,
        )
        return [self._format_exam_detail(e) for e in exams]

    def update_exam(self, exam_id: int, payload: ExamUpdate) -> ExamDetailRead:
        exam = self.exam_repo.get_by_id_with_details(exam_id)
        if not exam:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")

        # Determine new values
        pass_pct = payload.pass_percentage if payload.pass_percentage is not None else float(exam.pass_percentage)
        covered_cos = (
            [c.strip().upper() for c in payload.covered_cos]
            if payload.covered_cos is not None
            else [c.co_code for c in exam.covered_cos]
        )
        questions = (
            payload.questions
            if payload.questions is not None
            else [
                ExamQuestionConfig(
                    question_number=q.question_number,
                    max_marks=float(q.max_marks),
                    co_code=q.co_code,
                )
                for q in exam.questions
            ]
        )

        # Validate
        self._validate_exam_payload(
            department_id=exam.department_id,
            year_id=exam.year_id,
            semester_id=exam.semester_id,
            section_id=exam.section_id,
            subject_id=exam.subject_id,
            pass_percentage=pass_pct,
            covered_cos=covered_cos,
            questions=questions,
            exam_type=exam.exam_type,
            exam_name=payload.name or exam.name,
            batch_id=exam.batch_id,
            exclude_exam_id=exam.id,
        )

        clean_questions = [
            {
                "question_number": q.question_number.strip(),
                "max_marks": q.max_marks,
                "co_code": q.co_code.strip().upper(),
            }
            for q in questions
        ]

        updated = self.exam_repo.update_configuration(
            exam=exam,
            name=payload.name,
            exam_date=payload.exam_date or exam.exam_date,
            pass_percentage=pass_pct,
            covered_cos=covered_cos,
            questions=clean_questions,
        )
        return self._format_exam_detail(updated)

    def delete_exam(self, exam_id: int) -> bool:
        exam = self.exam_repo.get_by_id_with_details(exam_id)
        if not exam:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
        return self.exam_repo.delete_exam(exam)
