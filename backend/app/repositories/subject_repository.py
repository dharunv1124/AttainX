"""
Subject repository for master data persistence operations on subjects.
Subjects are scoped by Department, Year, and Semester.
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from app.db.models import (
    CourseCOAttainmentInputs,
    CourseCOPOMapping,
    Exam,
    ExamCoveredCO,
    ExamQuestion,
    StudentMark,
    Subject,
)
from app.repositories.base import BaseRepository


class SubjectRepository(BaseRepository[Subject]):
    def __init__(self, db: Session):
        super().__init__(Subject, db)

    def get_for_context(
        self,
        department_id: int,
        year_id: int,
        semester_id: int,
        batch_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
        include_inactive: bool = False,
    ) -> List[Subject]:
        query = self.db.query(Subject).filter(
            Subject.department_id == department_id,
            Subject.year_id == year_id,
            Subject.semester_id == semester_id,
        )
        if batch_id is not None:
            query = query.filter(Subject.batch_id == batch_id)
        if not include_inactive:
            query = query.filter(Subject.is_active.is_(True))
        return (
            query
            .order_by(Subject.name.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_name(
        self,
        name: str,
        department_id: int,
        year_id: int,
        semester_id: int,
        batch_id: Optional[int] = None,
    ) -> Optional[Subject]:
        query = self.db.query(Subject).filter(
            Subject.name == name.strip().upper(),
            Subject.department_id == department_id,
            Subject.year_id == year_id,
            Subject.semester_id == semester_id,
        )
        if batch_id is not None:
            query = query.filter(Subject.batch_id == batch_id)
        return query.first()

    def permanently_delete_archived(self, subject: Subject) -> None:
        try:
            exam_ids = [
                exam_id
                for (exam_id,) in self.db.query(Exam.id).filter(Exam.subject_id == subject.id).all()
            ]
            if exam_ids:
                self.db.query(StudentMark).filter(StudentMark.exam_id.in_(exam_ids)).delete(
                    synchronize_session=False
                )
                self.db.query(ExamQuestion).filter(ExamQuestion.exam_id.in_(exam_ids)).delete(
                    synchronize_session=False
                )
                self.db.query(ExamCoveredCO).filter(ExamCoveredCO.exam_id.in_(exam_ids)).delete(
                    synchronize_session=False
                )
                self.db.query(Exam).filter(Exam.id.in_(exam_ids)).delete(synchronize_session=False)

            self.db.query(CourseCOAttainmentInputs).filter(
                CourseCOAttainmentInputs.subject_id == subject.id
            ).delete(synchronize_session=False)
            self.db.query(CourseCOPOMapping).filter(
                CourseCOPOMapping.subject_id == subject.id
            ).delete(synchronize_session=False)
            self.db.delete(subject)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def create(self, name: str, department_id: int, year_id: int, semester_id: int, batch_id: Optional[int] = None) -> Subject:
        subject = Subject(
            name=name.strip().upper(),
            batch_id=batch_id,
            department_id=department_id,
            year_id=year_id,
            semester_id=semester_id,
        )
        self.db.add(subject)
        self.db.commit()
        self.db.refresh(subject)
        return subject

    def update(self, subject: Subject, name: str) -> Subject:
        subject.name = name.strip().upper()
        self.db.commit()
        self.db.refresh(subject)
        return subject
