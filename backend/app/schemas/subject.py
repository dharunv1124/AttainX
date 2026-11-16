"""
Subject Pydantic schemas.
Subject master data is scoped by Department, Year, and Semester, never Section.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class SubjectBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)


class SubjectCreate(SubjectBase):
    batch_id: Optional[int] = None
    department_id: int
    year_id: int
    semester_id: int


class SubjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=150)


class SubjectRead(SubjectBase):
    id: int
    batch_id: int
    department_id: Optional[int] = None
    year_id: Optional[int] = None
    semester_id: Optional[int] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
