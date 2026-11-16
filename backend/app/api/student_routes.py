"""
Student management API routes.
Students belong strictly to a Section (Department -> Year -> Section).
Students do NOT belong to a Subject.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_optional_user
from app.db.models import User, Student
from app.schemas.student import (
    StudentCreate,
    StudentUpdate,
    StudentRead,
    StudentDetailRead,
    StudentImportPreviewResult,
    StudentImportResult,
    StudentPlacementRead,
    StudentPlacementUpdate,
)
from app.services.student_service import StudentService

router = APIRouter(tags=["Students"])


def _to_detail_read(st: Student) -> StudentDetailRead:
    section = st.section
    current_placement = next(
        (placement for placement in st.academic_placements if placement.is_current),
        None,
    )
    placement_context = current_placement or (
        st.academic_placements[-1] if st.academic_placements else None
    )
    return StudentDetailRead(
        id=st.id,
        register_no=st.register_no,
        name=st.name,
        section_id=st.section_id,
        batch_id=st.batch_id,
        section_name=section.name if section else (
            placement_context.section_name if placement_context else None
        ),
        department_name=section.department.name if section else (
            placement_context.department.name if placement_context else None
        ),
        department_code=section.department.code if section else (
            placement_context.department.code if placement_context else None
        ),
        year_name=section.year.name if section else (
            placement_context.year.name if placement_context else None
        ),
        batch_name=st.batch.batch_name,
        placement_history=[
            StudentPlacementRead(
                id=placement.id,
                batch_id=placement.batch_id,
                department_id=placement.department_id,
                year_id=placement.year_id,
                semester_id=placement.semester_id,
                section_id=placement.section_id,
                section_name=placement.section.name if placement.section else placement.section_name,
                year_name=placement.year.name,
                semester_name=placement.semester.name if placement.semester else None,
                is_current=placement.is_current,
                effective_from=placement.effective_from,
                effective_to=placement.effective_to,
            )
            for placement in st.academic_placements
        ],
        archived_at=st.archived_at,
        created_at=st.created_at,
        updated_at=st.updated_at,
    )


@router.get("/students", response_model=List[StudentDetailRead])
def list_students(
    department_id: Optional[int] = None,
    year_id: Optional[int] = None,
    section_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """
    List students with optional cohort filtering:
    Department -> Year -> Section
    """
    students = StudentService(db).list_students(
        department_id=department_id,
        year_id=year_id,
        section_id=section_id,
        batch_id=batch_id,
        skip=skip,
        limit=limit,
    )
    return [_to_detail_read(s) for s in students]


@router.post("/students", response_model=StudentDetailRead, status_code=status.HTTP_201_CREATED)
def create_student(
    payload: StudentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """
    Add a new student to a designated section.
    Students belong exclusively to a Section (never to a Subject).
    """
    student = StudentService(db).create_student(payload)
    return _to_detail_read(student)


@router.get("/students/{student_id}", response_model=StudentDetailRead)
def get_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Retrieve a single student with class/section cohort details."""
    student = StudentService(db).get_student(student_id)
    return _to_detail_read(student)


@router.put("/students/{student_id}", response_model=StudentDetailRead)
def update_student(
    student_id: int,
    payload: StudentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Update a student's register number or name without changing its section."""
    student = StudentService(db).update_student(student_id, payload)
    return _to_detail_read(student)


@router.put("/students/{student_id}/placement", response_model=StudentDetailRead)
def move_student_placement(
    student_id: int,
    payload: StudentPlacementUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Move a stable student identity to a new section while retaining placement history."""
    return _to_detail_read(StudentService(db).move_student(student_id, payload))


@router.get("/students/{student_id}/placement-history", response_model=List[StudentPlacementRead])
def get_student_placement_history(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    return [
        StudentPlacementRead(
            id=placement.id,
            batch_id=placement.batch_id,
            department_id=placement.department_id,
            year_id=placement.year_id,
            semester_id=placement.semester_id,
            section_id=placement.section_id,
            section_name=placement.section.name if placement.section else placement.section_name,
            year_name=placement.year.name,
            semester_name=placement.semester.name if placement.semester else None,
            is_current=placement.is_current,
            effective_from=placement.effective_from,
            effective_to=placement.effective_to,
        )
        for placement in StudentService(db).get_student_placements(student_id)
    ]


@router.delete("/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Archive a student while preserving historical marks and relationships."""
    StudentService(db).archive_student(student_id)


@router.post("/students/{student_id}/restore", response_model=StudentDetailRead)
def restore_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Restore an archived student to the active section roster."""
    student = StudentService(db).restore_student(student_id)
    return _to_detail_read(student)


@router.delete("/students/{student_id}/permanent")
def permanently_delete_archived_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Permanently remove one archived student and that student's marks."""
    deleted_count = StudentService(db).permanently_delete_archived_student(student_id)
    return {"deleted_count": deleted_count}


@router.post("/students/import-preview", response_model=StudentImportPreviewResult)
def preview_student_import(
    section_id: int = Form(...),
    semester_id: Optional[int] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Validate a roster import before persisting it to the selected section."""
    return StudentService(db).preview_student_import(section_id, file, semester_id)


@router.post("/students/import", response_model=StudentImportResult)
def import_students(
    section_id: int = Form(...),
    semester_id: Optional[int] = Form(None),
    file: UploadFile = File(...),
    confirm: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Import valid new rows and restore eligible identities, leaving placement conflicts unchanged."""
    if not confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Confirmation is required before importing the student roster.")
    return StudentService(db).import_student_batch(section_id, file, semester_id)


@router.get("/sections/{section_id}/students", response_model=List[StudentDetailRead])
def get_section_students(
    section_id: int,
    include_archived: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """
    Directly retrieve all students enrolled in a specific class/section cohort.
    Used when an exam selects a Section to determine the student roster.
    """
    students = StudentService(db).get_students_by_section(section_id, include_archived=include_archived)
    return [_to_detail_read(s) for s in students]


@router.delete("/sections/{section_id}/students/archived")
def permanently_delete_archived_students(
    section_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Permanently remove archived students and their marks from one section."""
    deleted_count = StudentService(db).permanently_delete_archived_students(section_id)
    return {"deleted_count": deleted_count}
