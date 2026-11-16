"""
Exam repository for database operations on Exam configurations, covered COs, and questions.
"""

from datetime import date
from typing import Optional, List
from sqlalchemy.orm import Session, joinedload
from app.db.models import Exam, ExamCoveredCO, ExamQuestion
from app.repositories.base import BaseRepository


class ExamRepository(BaseRepository[Exam]):
    def __init__(self, db: Session):
        super().__init__(Exam, db)

    def get_by_id_with_details(self, exam_id: int) -> Optional[Exam]:
        """Fetch exam with all relationships eager-loaded."""
        return self.db.query(Exam).options(
            joinedload(Exam.department),
            joinedload(Exam.year),
            joinedload(Exam.semester),
            joinedload(Exam.section),
            joinedload(Exam.subject),
            joinedload(Exam.covered_cos),
            joinedload(Exam.questions),
        ).filter(Exam.id == exam_id).first()

    def get_all_filtered(
        self,
        department_id: Optional[int] = None,
        year_id: Optional[int] = None,
        semester_id: Optional[int] = None,
        section_id: Optional[int] = None,
        subject_id: Optional[int] = None,
        batch_id: Optional[int] = None,
    ) -> List[Exam]:
        query = self.db.query(Exam).options(
            joinedload(Exam.department),
            joinedload(Exam.year),
            joinedload(Exam.semester),
            joinedload(Exam.section),
            joinedload(Exam.subject),
            joinedload(Exam.covered_cos),
            joinedload(Exam.questions),
        )

        if batch_id is not None:
            query = query.filter(Exam.batch_id == batch_id)
        if department_id is not None:
            query = query.filter(Exam.department_id == department_id)
        if year_id is not None:
            query = query.filter(Exam.year_id == year_id)
        if semester_id is not None:
            query = query.filter(Exam.semester_id == semester_id)
        if section_id is not None:
            query = query.filter(Exam.section_id == section_id)
        if subject_id is not None:
            query = query.filter(Exam.subject_id == subject_id)

        return query.order_by(Exam.created_at.desc()).all()

    def delete_exam(self, exam: Exam) -> bool:
        try:
            self.db.delete(exam)
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            raise

    def create(
        self,
        name: str,
        exam_type: str,
        department_id: int,
        year_id: int,
        semester_id: int,
        section_id: int,
        subject_id: int,
        exam_date: date,
        pass_percentage: float,
        covered_cos: List[str],
        questions: List[dict],
        batch_id: Optional[int] = None,
    ) -> Exam:
        exam = Exam(
            name=name.strip(),
            exam_type=exam_type.strip().upper(),
            batch_id=batch_id,
            department_id=department_id,
            year_id=year_id,
            semester_id=semester_id,
            section_id=section_id,
            subject_id=subject_id,
            exam_date=exam_date,
            pass_percentage=pass_percentage,
        )
        self.db.add(exam)
        self.db.flush()  # obtain exam.id

        # Add covered COs
        for co in covered_cos:
            cov = ExamCoveredCO(exam_id=exam.id, co_code=co.strip().upper())
            self.db.add(cov)

        # Add questions
        for q in questions:
            question = ExamQuestion(
                exam_id=exam.id,
                question_number=q["question_number"].strip(),
                max_marks=q["max_marks"],
                co_code=q["co_code"].strip().upper(),
            )
            self.db.add(question)

        self.db.commit()
        return self.get_by_id_with_details(exam.id) or exam

    def update_configuration(
        self,
        exam: Exam,
        name: Optional[str] = None,
        exam_date: Optional[date] = None,
        pass_percentage: Optional[float] = None,
        covered_cos: Optional[List[str]] = None,
        questions: Optional[List[dict]] = None,
    ) -> Exam:
        if name is not None:
            exam.name = name.strip()
        if exam_date is not None:
            exam.exam_date = exam_date
        if pass_percentage is not None:
            exam.pass_percentage = pass_percentage

        if covered_cos is not None:
            # Replace covered COs
            self.db.query(ExamCoveredCO).filter(ExamCoveredCO.exam_id == exam.id).delete()
            for co in covered_cos:
                cov = ExamCoveredCO(exam_id=exam.id, co_code=co.strip().upper())
                self.db.add(cov)

        if questions is not None:
            # Replace questions
            self.db.query(ExamQuestion).filter(ExamQuestion.exam_id == exam.id).delete()
            for q in questions:
                question = ExamQuestion(
                    exam_id=exam.id,
                    question_number=q["question_number"].strip(),
                    max_marks=q["max_marks"],
                    co_code=q["co_code"].strip().upper(),
                )
                self.db.add(question)

        self.db.commit()
        return self.get_by_id_with_details(exam.id) or exam
