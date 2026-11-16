"""
Academic structure schemas: Year, Semester, and Section.
Sections are scoped by Department and Year, independently of Semester.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


# ---------------- Batches ----------------
class BatchRead(BaseModel):
    id: int
    batch_name: str
    start_year: int
    end_year: int
    is_active: bool = True
    is_default: bool = False

    model_config = ConfigDict(from_attributes=True)


class DeletionStatus(BaseModel):
    can_delete: bool
    reason: Optional[str] = None


class SectionDeletionStatus(DeletionStatus):
    student_count: int
    placement_count: int
    student_mark_count: int
    exam_count: int
    exam_question_count: int
    exam_covered_co_count: int
    course_co_po_mapping_count: int
    course_co_attainment_input_count: int
    student_ids_to_delete: List[int]
    student_ids_preserved: List[int]
    plan_token: str


class BatchCreate(BaseModel):
    batch_name: str = Field(..., min_length=2, max_length=50)
    start_year: int = Field(..., ge=2000, le=2100)
    end_year: int = Field(..., ge=2000, le=2100)
    is_active: bool = True


class BatchUpdate(BaseModel):
    batch_name: Optional[str] = Field(default=None, min_length=2, max_length=50)
    start_year: Optional[int] = Field(default=None, ge=2000, le=2100)
    end_year: Optional[int] = Field(default=None, ge=2000, le=2100)
    is_active: Optional[bool] = None


# ---------------- Years ----------------
class YearRead(BaseModel):
    id: int
    year_number: int
    name: str

    model_config = ConfigDict(from_attributes=True)


# ---------------- Semesters ----------------
class SemesterRead(BaseModel):
    id: int
    semester_number: int
    name: str
    year_id: int

    model_config = ConfigDict(from_attributes=True)


# ---------------- Sections ----------------
class SectionBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=20)
    batch_id: Optional[int] = None
    department_id: int
    year_id: int


class SectionCreate(SectionBase):
    pass


class SectionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=20)
    batch_id: Optional[int] = None
    department_id: Optional[int] = None
    year_id: Optional[int] = None


class SectionRead(SectionBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SectionDetailRead(SectionRead):
    department_name: str
    department_code: str
    year_name: str
    batch_name: Optional[str] = None
