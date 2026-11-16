"""
Subject service managing subject master data.
Contains Subject Name only, independent of students.
"""

from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import Subject
from app.repositories.department_repository import DepartmentRepository
from app.repositories.academic_repository import BatchRepository, YearRepository, SemesterRepository
from app.repositories.subject_repository import SubjectRepository
from app.schemas.subject import SubjectCreate, SubjectUpdate


class SubjectService:
    def __init__(self, db: Session):
        self.db = db
        self.subject_repo = SubjectRepository(db)
        self.batch_repo = BatchRepository(db)
        self.department_repo = DepartmentRepository(db)
        self.year_repo = YearRepository(db)
        self.semester_repo = SemesterRepository(db)

    def _validate_context(self, department_id: int, year_id: int, semester_id: int, batch_id: Optional[int] = None) -> None:
        if batch_id is not None and not self.batch_repo.get_by_id(batch_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")
        if not self.department_repo.get(department_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
        if not self.year_repo.get_by_id(year_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Year not found")
        semester = self.semester_repo.get_by_id(semester_id)
        if not semester:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Semester not found")
        if semester.year_id != year_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected Semester does not belong to the selected Year",
            )

    def list_subjects(
        self,
        department_id: int,
        year_id: int,
        semester_id: int,
        batch_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
        include_inactive: bool = False,
    ) -> List[Subject]:
        batch_id = self._resolve_batch_id(batch_id)
        self._validate_context(department_id, year_id, semester_id, batch_id=batch_id)
        return self.subject_repo.get_for_context(
            department_id=department_id,
            year_id=year_id,
            semester_id=semester_id,
            batch_id=batch_id,
            skip=skip,
            limit=limit,
            include_inactive=include_inactive,
        )

    def get_subject(self, subject_id: int) -> Subject:
        subject = self.subject_repo.get(subject_id)
        if not subject:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
        return subject

    def create_subject(self, payload: SubjectCreate) -> Subject:
        name = payload.name.strip().upper()
        batch_id = self._resolve_batch_id(payload.batch_id)
        self._validate_context(payload.department_id, payload.year_id, payload.semester_id, batch_id=batch_id)
        existing = self.subject_repo.get_by_name(
            name,
            department_id=payload.department_id,
            year_id=payload.year_id,
            semester_id=payload.semester_id,
            batch_id=batch_id,
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Subject '{name}' already exists",
            )
        return self.subject_repo.create(
            name=name,
            department_id=payload.department_id,
            year_id=payload.year_id,
            semester_id=payload.semester_id,
            batch_id=batch_id,
        )

    def _resolve_batch_id(self, batch_id: Optional[int]) -> int:
        if batch_id is not None:
            return batch_id
        default_batch = self.batch_repo.get_default()
        if default_batch is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The default 2024–28 Batch is not configured or active.")
        return default_batch.id

    def update_subject(self, subject_id: int, payload: SubjectUpdate) -> Subject:
        subject = self.get_subject(subject_id)
        if payload.name:
            name = payload.name.strip().upper()
            existing = None
            if subject.department_id is not None:
                existing = self.subject_repo.get_by_name(
                    name,
                    department_id=subject.department_id,
                    year_id=subject.year_id,
                    semester_id=subject.semester_id,
                    batch_id=subject.batch_id,
                )
            if existing and existing.id != subject_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Subject '{name}' already exists in this academic context",
                )
            return self.subject_repo.update(subject, name=name)
        return subject

    def delete_subject(self, subject_id: int) -> bool:
        subject = self.get_subject(subject_id)
        if subject.is_active:
            subject.is_active = False
            self.db.commit()
            self.db.refresh(subject)
        return True

    def permanently_delete_archived_subject(self, subject_id: int) -> None:
        subject = self.db.query(Subject).filter(
            Subject.id == subject_id
        ).with_for_update().first()
        if subject is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
        if subject.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only archived subjects can be permanently deleted.",
            )

        self.subject_repo.permanently_delete_archived(subject)

    def restore_subject(
        self,
        subject_id: int,
        department_id: int,
        year_id: int,
        semester_id: int,
        batch_id: Optional[int] = None,
    ) -> Subject:
        batch_id = self._resolve_batch_id(batch_id)
        self._validate_context(department_id, year_id, semester_id, batch_id=batch_id)
        subject = self.get_subject(subject_id)
        if (subject.batch_id, subject.department_id, subject.year_id, subject.semester_id) != (
            batch_id,
            department_id,
            year_id,
            semester_id,
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subject not found in the selected academic context",
            )
        if not subject.is_active:
            subject.is_active = True
            self.db.commit()
            self.db.refresh(subject)
        return subject
