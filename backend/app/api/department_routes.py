"""
Department master data API routes.
"""

from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_optional_user
from app.db.models import User
from app.schemas.department import DepartmentCreate, DepartmentUpdate, DepartmentRead
from app.services.master_data_service import MasterDataService

router = APIRouter(prefix="/departments", tags=["Departments"])


@router.get("", response_model=List[DepartmentRead])
def list_departments(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """List all departments."""
    return MasterDataService(db).list_departments(skip=skip, limit=limit)


@router.post("", response_model=DepartmentRead, status_code=status.HTTP_201_CREATED)
def create_department(
    payload: DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Create a new department."""
    return MasterDataService(db).create_department(payload)


@router.get("/{dept_id}", response_model=DepartmentRead)
def get_department(
    dept_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Retrieve department by ID."""
    return MasterDataService(db).get_department(dept_id)


@router.put("/{dept_id}", response_model=DepartmentRead)
def update_department(
    dept_id: int,
    payload: DepartmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Update department name or code."""
    return MasterDataService(db).update_department(dept_id, payload)


@router.delete("/{dept_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_department(
    dept_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Delete a department."""
    MasterDataService(db).delete_department(dept_id)
