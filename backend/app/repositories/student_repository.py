"""Persistence for batch-scoped student identities and placement history."""

import re
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.db.models import (
    Semester,
    Student,
    StudentAcademicPlacement,
    StudentMark,
    Section,
)
from app.repositories.base import BaseRepository


class StudentRepository(BaseRepository[Student]):
    def __init__(self, db: Session):
        super().__init__(Student, db)

    def get_by_register_no(
        self,
        register_no: str,
        batch_id: int,
        section_id: Optional[int] = None,
        exclude_student_id: Optional[int] = None,
        lock: bool = False,
    ) -> Optional[Student]:
        query = self.db.query(Student).options(
            joinedload(Student.section).joinedload(Section.department),
            joinedload(Student.section).joinedload(Section.year),
            joinedload(Student.batch),
        ).filter(func.upper(func.trim(Student.register_no)) == register_no.strip().upper())
        query = query.filter(Student.batch_id == batch_id)
        if section_id is not None:
            query = query.join(
                StudentAcademicPlacement,
                StudentAcademicPlacement.student_id == Student.id,
            ).filter(
                StudentAcademicPlacement.section_id == section_id,
                StudentAcademicPlacement.is_current.is_(True),
            )
        if exclude_student_id is not None:
            query = query.filter(Student.id != exclude_student_id)
        if lock:
            query = query.with_for_update(of=Student)
        return query.first()

    def get_all_by_register_no(
        self,
        register_no: str,
        batch_id: int,
        lock: bool = False,
    ) -> List[Student]:
        query = self.db.query(Student).options(
            joinedload(Student.section).joinedload(Section.department),
            joinedload(Student.section).joinedload(Section.year),
            joinedload(Student.batch),
        ).filter(
            func.upper(func.trim(Student.register_no)) == register_no.strip().upper(),
            Student.batch_id == batch_id,
        )
        if lock:
            query = query.with_for_update(of=Student)
        return query.all()

    @staticmethod
    def _natural_register_key(student: Student):
        parts = re.split(r"(\d+)", student.register_no.casefold())
        natural_parts = tuple(
            (1, int(part)) if part.isdigit() else (0, part)
            for part in parts
        )
        return natural_parts, student.register_no.casefold(), student.id

    def count_marks(self, student_id: int) -> int:
        return self.db.query(StudentMark).filter(StudentMark.student_id == student_id).count()

    def get_by_id_with_details(self, student_id: int) -> Optional[Student]:
        return self.db.query(Student).options(
            joinedload(Student.section).joinedload(Section.department),
            joinedload(Student.section).joinedload(Section.year),
            joinedload(Student.batch),
            joinedload(Student.academic_placements).joinedload(StudentAcademicPlacement.semester),
        ).filter(Student.id == student_id).first()

    def get_by_id_for_update(self, student_id: int) -> Optional[Student]:
        return self.db.query(Student).filter(
            Student.id == student_id
        ).with_for_update().first()

    def get_placements(self, student_id: int) -> List[StudentAcademicPlacement]:
        return self.db.query(StudentAcademicPlacement).options(
            joinedload(StudentAcademicPlacement.department),
            joinedload(StudentAcademicPlacement.year),
            joinedload(StudentAcademicPlacement.semester),
            joinedload(StudentAcademicPlacement.section),
        ).filter(
            StudentAcademicPlacement.student_id == student_id
        ).order_by(
            StudentAcademicPlacement.effective_from,
            StudentAcademicPlacement.id,
        ).all()

    def get_current_placement(
        self,
        student_id: int,
        lock: bool = False,
    ) -> Optional[StudentAcademicPlacement]:
        query = self.db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id == student_id,
            StudentAcademicPlacement.is_current.is_(True),
        )
        if lock:
            query = query.with_for_update()
        return query.first()

    def get_latest_placement(self, student_id: int) -> Optional[StudentAcademicPlacement]:
        return self.db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id == student_id,
        ).order_by(
            StudentAcademicPlacement.effective_from.desc(),
            StudentAcademicPlacement.id.desc(),
        ).first()

    def get_by_section_id(self, section_id: int, include_archived: bool = False) -> List[Student]:
        """Retrieve identities assigned to the selected Batch/Department/cohort section."""
        target = self.db.query(Section).filter(Section.id == section_id).first()
        if target is None:
            return []
        query = self.db.query(Student).join(
            Section,
            Student.section_id == Section.id,
        ).options(
            joinedload(Student.section).joinedload(Section.department),
            joinedload(Student.section).joinedload(Section.year),
            joinedload(Student.batch),
        ).filter(
            Student.batch_id == target.batch_id,
            Section.batch_id == target.batch_id,
            Section.department_id == target.department_id,
            Section.name == target.name,
        )
        if not include_archived:
            query = query.filter(Student.archived_at.is_(None))
        students = query.all()
        return sorted(students, key=self._natural_register_key)

    def filter_students(
        self,
        department_id: Optional[int] = None,
        year_id: Optional[int] = None,
        section_id: Optional[int] = None,
        batch_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
        include_archived: bool = False,
    ) -> List[Student]:
        query = self.db.query(Student).join(
            StudentAcademicPlacement,
            StudentAcademicPlacement.student_id == Student.id,
        ).join(
            Section,
            Section.id == StudentAcademicPlacement.section_id,
        ).options(
            joinedload(Student.section).joinedload(Section.department),
            joinedload(Student.section).joinedload(Section.year),
            joinedload(Student.batch),
        ).filter(StudentAcademicPlacement.is_current.is_(True))

        if batch_id is not None:
            query = query.filter(Student.batch_id == batch_id)
        if section_id is not None:
            query = query.filter(StudentAcademicPlacement.section_id == section_id)
        if department_id is not None:
            query = query.filter(StudentAcademicPlacement.department_id == department_id)
        if year_id is not None:
            query = query.filter(StudentAcademicPlacement.year_id == year_id)
        if not include_archived:
            query = query.filter(Student.archived_at.is_(None))
        students = sorted(query.all(), key=self._natural_register_key)
        return students[skip:skip + limit]

    def set_archived(self, student: Student, archived: bool, commit: bool = True) -> Student:
        student.archived_at = datetime.now(timezone.utc) if archived else None
        if commit:
            self.db.commit()
            self.db.refresh(student)
        return self.get_by_id_with_details(student.id) or student

    def permanently_delete_archived_in_section(
        self,
        section_id: int,
        student_id: Optional[int] = None,
    ) -> int:
        target = self.db.query(Section).filter(Section.id == section_id).first()
        if target is None:
            return 0
        archived_query = self.db.query(Student.id).join(
            Section,
            Student.section_id == Section.id,
        ).filter(
            Section.batch_id == target.batch_id,
            Section.department_id == target.department_id,
            Section.name == target.name,
            Student.archived_at.is_not(None),
        )
        if student_id is not None:
            archived_query = archived_query.filter(Student.id == student_id)
        archived_ids = [student_id for (student_id,) in archived_query.with_for_update().all()]
        if not archived_ids:
            return 0

        self.db.query(StudentMark).filter(StudentMark.student_id.in_(archived_ids)).delete(
            synchronize_session=False
        )
        return self.db.query(Student).filter(
            Student.id.in_(archived_ids),
            Student.archived_at.is_not(None),
        ).delete(synchronize_session=False)

    def create(
        self,
        register_no: str,
        name: str,
        batch_id: int,
        section: Section,
        semester_id: Optional[int] = None,
        commit: bool = True,
    ) -> Student:
        student = Student(
            register_no=register_no.strip().upper(),
            name=name.strip(),
            batch_id=batch_id,
            section_id=section.id,
        )
        self.db.add(student)
        self.db.flush()
        self._add_placement(student, section, semester_id=semester_id)
        if commit:
            self.db.commit()
            self.db.refresh(student)
        return self.get_by_id_with_details(student.id) or student

    def move_to_section(
        self,
        student: Student,
        section: Section,
        semester_id: Optional[int] = None,
        effective_from: Optional[datetime] = None,
        commit: bool = True,
    ) -> Student:
        now = effective_from or datetime.now(timezone.utc)
        current = self.get_current_placement(student.id, lock=True)
        if current and current.section_id == section.id and (
            semester_id is None or current.semester_id == semester_id
        ):
            if current.section_name != section.name:
                current.section_name = section.name
            return self.get_by_id_with_details(student.id) or student
        if current:
            current.is_current = False
            current.effective_to = now
            self.db.flush()
        student.section_id = section.id
        student.section = section
        self._add_placement(student, section, semester_id=semester_id, effective_from=now)
        if commit:
            self.db.commit()
        return self.get_by_id_with_details(student.id) or student

    def _add_placement(
        self,
        student: Student,
        section: Section,
        semester_id: Optional[int],
        effective_from: Optional[datetime] = None,
    ) -> StudentAcademicPlacement:
        if semester_id is None:
            semester_id = self.db.query(Semester.id).filter(
                Semester.year_id == section.year_id
            ).order_by(Semester.semester_number).limit(1).scalar()
        placement = StudentAcademicPlacement(
            student_id=student.id,
            batch_id=student.batch_id,
            department_id=section.department_id,
            year_id=section.year_id,
            semester_id=semester_id,
            section_id=section.id,
            section_name=section.name,
            is_current=True,
            effective_from=effective_from or datetime.now(timezone.utc),
        )
        self.db.add(placement)
        return placement

    def update(
        self,
        student: Student,
        register_no: str,
        name: str,
    ) -> Student:
        student.register_no = register_no.strip().upper()
        student.name = name.strip()
        self.db.commit()
        self.db.refresh(student)
        return self.get_by_id_with_details(student.id) or student
