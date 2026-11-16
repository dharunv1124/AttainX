"""
Student Pydantic schemas.
Students belong strictly to a Section (Department -> Year -> Section).
Students do NOT belong to a Subject.
Fields strictly limited to: Register Number, Name, Section.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class StudentBase(BaseModel):
    register_no: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=2, max_length=100)
    section_id: Optional[int] = None
    batch_id: Optional[int] = None


class StudentCreate(StudentBase):
    section_id: int
    semester_id: Optional[int] = None


class StudentUpdate(BaseModel):
    register_no: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)


class StudentRead(StudentBase):
    id: int
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class StudentPlacementRead(BaseModel):
    id: int
    batch_id: int
    department_id: int
    year_id: int
    semester_id: Optional[int] = None
    section_id: Optional[int] = None
    section_name: Optional[str] = None
    year_name: str
    semester_name: Optional[str] = None
    is_current: bool
    effective_from: datetime
    effective_to: Optional[datetime] = None


class StudentDetailRead(StudentRead):
    section_name: Optional[str] = None
    department_name: Optional[str] = None
    department_code: Optional[str] = None
    year_name: Optional[str] = None
    batch_name: str
    placement_history: List[StudentPlacementRead] = Field(default_factory=list)


class StudentPlacementUpdate(BaseModel):
    section_id: int
    semester_id: Optional[int] = None


class StudentImportIdentityResolution(BaseModel):
    row_number: int
    register_no: str
    uploaded_name: str
    selected_student_id: Optional[int] = None
    selected_student_name: Optional[str] = None
    candidate_student_ids: List[int] = Field(default_factory=list)
    other_student_ids: List[int] = Field(default_factory=list)
    resolution_status: str
    destination_section_id: int
    destination_section_name: str


class StudentImportPreviewResult(BaseModel):
    section_id: int
    batch_id: int
    total_rows: int
    valid_rows: int
    invalid_rows: int
    new_students: int = 0
    already_assigned: int = 0
    eligible_for_restoration: int = 0
    placement_conflicts: int = 0
    duplicate_register_numbers: List[str] = Field(default_factory=list)
    identity_resolutions: List[StudentImportIdentityResolution] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class StudentImportResult(BaseModel):
    section_id: int
    batch_id: int
    imported_count: int
    restored_count: int = 0
    already_assigned_count: int = 0
    placed_count: int = 0
    skipped_conflict_count: int = 0
    message: str
