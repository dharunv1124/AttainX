"""
Marks Repository for Phase 6.
Handles persistence and retrieval of student question-wise marks for exams.
"""

from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from app.db.models import StudentMark, Student
from app.repositories.base import BaseRepository


class MarksRepository(BaseRepository[StudentMark]):
    def __init__(self, db: Session):
        super().__init__(StudentMark, db)

    def get_by_exam(self, exam_id: int) -> List[StudentMark]:
        """Fetch all marks entered for an exam ordered by student and question."""
        return (
            self.db.query(StudentMark)
            .filter(StudentMark.exam_id == exam_id)
            .join(Student, StudentMark.student_id == Student.id)
            .order_by(Student.register_no, StudentMark.question_number)
            .all()
        )

    def upsert_student_mark(
        self,
        exam_id: int,
        student_id: int,
        question_number: str,
        obtained_mark: float,
    ) -> StudentMark:
        """Insert or update a student's obtained mark for a specific question."""
        existing = (
            self.db.query(StudentMark)
            .filter(
                StudentMark.exam_id == exam_id,
                StudentMark.student_id == student_id,
                StudentMark.question_number == question_number,
            )
            .first()
        )
        if existing:
            existing.obtained_mark = obtained_mark
            self.db.commit()
            self.db.refresh(existing)
            return existing

        mark = StudentMark(
            exam_id=exam_id,
            student_id=student_id,
            question_number=question_number,
            obtained_mark=obtained_mark,
        )
        self.db.add(mark)
        self.db.commit()
        self.db.refresh(mark)
        return mark

    def delete_by_exam(self, exam_id: int) -> int:
        """Delete all marks for an exam."""
        deleted = (
            self.db.query(StudentMark)
            .filter(StudentMark.exam_id == exam_id)
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted
