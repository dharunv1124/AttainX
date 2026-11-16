"""
Pydantic schemas for Phase 6: Student Marks Entry and CO Results.
"""

from typing import List, Dict, Optional, Union
from pydantic import BaseModel, Field, model_validator


class StudentMarkInput(BaseModel):
    register_no: str
    question_id: Optional[int] = None
    question_number: Optional[str] = None
    obtained_mark: float = Field(..., ge=0.0, description="Obtained mark, non-negative and <= question max")

    @model_validator(mode="after")
    def require_question_reference(self):
        if self.question_id is None and not self.question_number:
            raise ValueError("A configured question_id or question_number is required")
        return self


class MarksSaveRequest(BaseModel):
    marks: List[StudentMarkInput]


class StudentCOResultSchema(BaseModel):
    co_code: str
    co_max_marks: float
    obtained_marks: float
    co_percentage: float
    attainment: int  # 1 or 0 strictly


class StudentResultRowSchema(BaseModel):
    register_no: str
    name: str
    question_marks: Dict[str, float]
    total_obtained: float
    co_results: Dict[str, StudentCOResultSchema]


class ExamCalculationResponse(BaseModel):
    exam_id: Union[int, str]
    pass_percentage: float
    covered_cos: List[str]
    co_max_marks: Dict[str, float]
    students: List[StudentResultRowSchema]
