"""
Academic structure API routes (Years, Semesters, Sections).
Sections are selected by Department and Year.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_optional_user
from app.db.models import User
from app.schemas.academic import (
    BatchRead,
    BatchUpdate,
    DeletionStatus,
    SectionDeletionStatus,
    YearRead,
    SemesterRead,
    SectionCreate,
    SectionUpdate,
    SectionRead,
    SectionDetailRead,
)
from app.services.master_data_service import MasterDataService

router = APIRouter(prefix="/academic", tags=["Academic Structure"])


class BatchCreateRequest(BaseModel):
    batch_name: str = Field(..., min_length=2, max_length=50)
    is_active: bool = True


# ---------------- Batches ----------------
@router.get("/batches", response_model=List[BatchRead])
def list_batches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """List all configured academic batches."""
    return MasterDataService(db).list_batches()


@router.post("/batches", response_model=BatchRead, status_code=status.HTTP_201_CREATED)
def create_batch(
    payload: BatchCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Create a new academic batch."""
    return MasterDataService(db).create_batch(payload)


@router.put("/batches/{batch_id}", response_model=BatchRead)
def update_batch(
    batch_id: int,
    payload: BatchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Update batch display, year range, or active status."""
    return MasterDataService(db).update_batch(batch_id, payload)


@router.get("/batches/{batch_id}", response_model=BatchRead)
def get_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Get a specific academic batch."""
    return MasterDataService(db).get_batch(batch_id)


@router.get("/batches/{batch_id}/deletion-status", response_model=DeletionStatus)
def get_batch_deletion_status(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    return MasterDataService(db).get_batch_deletion_status(batch_id)


@router.delete("/batches/{batch_id}")
def delete_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Permanently delete a batch and its batch-owned academic records."""
    return MasterDataService(db).delete_batch(batch_id)


# ---------------- Years ----------------
@router.get("/years", response_model=List[YearRead])
def list_years(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """List the academic years (1st Year, 2nd Year, 3rd Year, 4th Year)."""
    return MasterDataService(db).list_years()


# ---------------- Semesters ----------------
@router.get("/semesters", response_model=List[SemesterRead])
def list_semesters(
    year_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """List semesters (1 through 8), optionally filtered by year."""
    return MasterDataService(db).list_semesters(year_id=year_id)


# ---------------- Sections ----------------
@router.get("/sections", response_model=List[SectionDetailRead])
def list_sections(
    department_id: Optional[int] = None,
    year_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """List sections, optionally filtered by Batch, Department, and Year."""
    sections = MasterDataService(db).list_sections(
        department_id=department_id,
        year_id=year_id,
        batch_id=batch_id,
    )
    return [
        SectionDetailRead(
            id=s.id,
            name=s.name,
            batch_id=s.batch_id,
            department_id=s.department_id,
            year_id=s.year_id,
            department_name=s.department.name,
            department_code=s.department.code,
            year_name=s.year.name,
            batch_name=s.batch.batch_name if s.batch else None,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in sections
    ]


@router.post("/sections", response_model=SectionRead, status_code=status.HTTP_201_CREATED)
def create_section(
    payload: SectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Create a new section under a Department and Year."""
    return MasterDataService(db).create_section(payload)


@router.get("/sections/{section_id}", response_model=SectionDetailRead)
def get_section(
    section_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Get section details by ID."""
    s = MasterDataService(db).get_section(section_id)
    return SectionDetailRead(
        id=s.id,
        name=s.name,
        batch_id=s.batch_id,
        department_id=s.department_id,
        year_id=s.year_id,
        department_name=s.department.name,
        department_code=s.department.code,
        year_name=s.year.name,
        batch_name=s.batch.batch_name if s.batch else None,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@router.put("/sections/{section_id}", response_model=SectionRead)
def update_section(
    section_id: int,
    payload: SectionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Update section information."""
    return MasterDataService(db).update_section(section_id, payload)


@router.delete("/sections/{section_id}")
def delete_section(
    section_id: int,
    plan_token: str = Query(..., min_length=64, max_length=64),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Permanently delete a section and its owned student and academic records."""
    return MasterDataService(db).delete_section(section_id, plan_token)


@router.get(
    "/sections/{section_id}/deletion-status",
    response_model=SectionDeletionStatus,
)
def get_section_deletion_status(
    section_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    return MasterDataService(db).get_section_deletion_status(section_id)
