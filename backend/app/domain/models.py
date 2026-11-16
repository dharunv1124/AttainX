"""
Pure domain models for CO-based OBE calculation.
Zero framework or database dependencies.
"""

from dataclasses import dataclass, field
from typing import Union, Sequence, Mapping, Optional


@dataclass(frozen=True)
class Question:
    """Represents a configured question in an exam."""
    question_number: str
    max_marks: float
    mapped_co: str


@dataclass(frozen=True)
class Student:
    """Represents minimal student identity required for calculation and reporting."""
    register_no: str
    name: str


@dataclass(frozen=True)
class StudentQuestionMark:
    """Represents an obtained mark for a specific student on a specific question."""
    register_no: str
    question_number: str
    obtained_mark: float


@dataclass(frozen=True)
class ExamCalculationInput:
    """
    Complete calculation payload for an exam.
    Input boundary to the domain calculation engine.
    """
    exam_id: Union[str, int]
    pass_percentage: float
    covered_cos: Sequence[str]
    questions: Sequence[Question]
    students: Sequence[Student]
    marks: Sequence[StudentQuestionMark]


@dataclass(frozen=True)
class StudentCOResult:
    """Calculated outcome attainment for a single student on a single CO."""
    co_code: str
    co_max_marks: float
    obtained_marks: float
    co_percentage: float
    attainment: int  # Strictly 1 or 0


@dataclass(frozen=True)
class StudentExamResult:
    """Complete calculated result row for a student in an exam."""
    register_no: str
    name: str
    question_marks: Mapping[str, float]  # question_number -> obtained_mark
    total_obtained: float
    co_results: Mapping[str, StudentCOResult]  # co_code -> StudentCOResult


@dataclass(frozen=True)
class OverallCOAttainment:
    """Overall attainment level for a CO across the exam cohort."""
    co_code: str
    total_students: int
    students_attaining_co: int
    attainment_percentage: float
    attainment_level: Optional[int]


@dataclass(frozen=True)
class CanonicalExamResult:
    """
    Canonical output of the CO calculation engine.
    Single source of truth consumed by UI, Excel export, and PDF export.
    """
    exam_id: Union[str, int]
    pass_percentage: float
    covered_cos: Sequence[str]
    co_max_marks: Mapping[str, float]  # co_code -> total maximum marks
    students: Sequence[StudentExamResult]
    overall_co_attainment: Mapping[str, OverallCOAttainment] = field(default_factory=dict)
