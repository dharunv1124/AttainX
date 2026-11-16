"""
Subject master data API routes.
Subjects are filtered by Department, Year, and Semester, not Section.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_optional_user
from app.db.models import User
from app.schemas.subject import SubjectCreate, SubjectUpdate, SubjectRead
from app.services.subject_service import SubjectService

router = APIRouter(prefix="/subjects", tags=["Subjects"])


@router.get("", response_model=List[SubjectRead])
def list_subjects(
    department_id: int,
    year_id: int,
    semester_id: int,
    batch_id: Optional[int] = None,
    include_inactive: bool = False,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """List subjects for a Department, Year, Semester, and optional Batch."""
    return SubjectService(db).list_subjects(
        department_id=department_id,
        year_id=year_id,
        semester_id=semester_id,
        batch_id=batch_id,
        include_inactive=include_inactive,
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=SubjectRead, status_code=status.HTTP_201_CREATED)
def create_subject(
    payload: SubjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Create a new subject."""
    return SubjectService(db).create_subject(payload)


@router.get("/{subject_id}", response_model=SubjectRead)
def get_subject(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Retrieve subject by ID."""
    return SubjectService(db).get_subject(subject_id)


@router.put("/{subject_id}", response_model=SubjectRead)
def update_subject(
    subject_id: int,
    payload: SubjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Update subject name."""
    return SubjectService(db).update_subject(subject_id, payload)


@router.delete("/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Archive a subject without removing its historical references."""
    SubjectService(db).delete_subject(subject_id)


@router.delete("/{subject_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
def permanently_delete_archived_subject(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Permanently delete one archived subject only when no history depends on it."""
    SubjectService(db).permanently_delete_archived_subject(subject_id)


@router.post("/{subject_id}/restore", response_model=SubjectRead)
def restore_subject(
    subject_id: int,
    department_id: int,
    year_id: int,
    semester_id: int,
    batch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Restore a subject within its original academic context."""
    return SubjectService(db).restore_subject(
        subject_id=subject_id,
        department_id=department_id,
        year_id=year_id,
        semester_id=semester_id,
        batch_id=batch_id,
    )
