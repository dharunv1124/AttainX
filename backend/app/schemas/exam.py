"""
Exam configuration schemas for Phase 5.
Supports the faculty workflow:
Class Selection -> Subject Selection -> Exam Details -> Covered COs -> Pass Percentage -> Question Configuration.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


class ExamQuestionConfig(BaseModel):
    id: Optional[int] = None
    question_number: str = Field(..., min_length=1, max_length=20)
    max_marks: float = Field(..., gt=0)
    co_code: str = Field(..., min_length=2, max_length=20)

    model_config = ConfigDict(from_attributes=True)

    @field_validator("question_number")
    def clean_question_number(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Question number cannot be empty")
        return s

    @field_validator("co_code")
    def clean_co_code(cls, v: str) -> str:
        s = v.strip().upper()
        if not s:
            raise ValueError("CO code cannot be empty")
        return s


class ExamCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    exam_date: date
    exam_type: str = Field(default="CUSTOM", max_length=50)  # INTERNAL_1, INTERNAL_2, MODEL, CUSTOM
    batch_id: Optional[int] = None
    department_id: int
    year_id: int
    semester_id: int
    section_id: int
    subject_id: int
    pass_percentage: float = Field(..., gt=0, le=100)
    covered_cos: List[str] = Field(..., min_length=1)
    questions: List[ExamQuestionConfig] = Field(..., min_length=1)


class ExamUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    exam_date: Optional[date] = None
    pass_percentage: Optional[float] = Field(default=None, gt=0, le=100)
    covered_cos: Optional[List[str]] = Field(default=None, min_length=1)
    questions: Optional[List[ExamQuestionConfig]] = Field(default=None, min_length=1)


class ExamRead(BaseModel):
    id: int
    name: str
    exam_date: Optional[date]
    exam_type: str
    batch_id: Optional[int] = None
    department_id: int
    year_id: int
    semester_id: int
    section_id: int
    subject_id: int
    pass_percentage: float
    covered_cos: List[str]
    questions: List[ExamQuestionConfig]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExamDetailRead(ExamRead):
    department_name: str
    department_code: str
    year_name: str
    semester_name: str
    section_name: str
    subject_name: str
    total_marks: float
    total_questions: int
    student_count: int
