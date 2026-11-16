"""
Pure CO Domain Model and Authoritative Calculation Engine.
Single source of truth for Course Outcome attainment calculations.
Zero external dependencies (standard library Python only).
"""

from app.domain.models import (
    Question,
    Student,
    StudentQuestionMark,
    ExamCalculationInput,
    StudentCOResult,
    StudentExamResult,
    CanonicalExamResult,
)
from app.domain.errors import (
    DomainValidationError,
    InvalidMarkError,
    InvalidQuestionConfigurationError,
    InvalidExamConfigurationError,
    IncompleteDataError,
)
from app.domain.engine import (
    calculate_exam_co_attainment,
    validate_calculation_input,
)

__all__ = [
    "Question",
    "Student",
    "StudentQuestionMark",
    "ExamCalculationInput",
    "StudentCOResult",
    "StudentExamResult",
    "CanonicalExamResult",
    "DomainValidationError",
    "InvalidMarkError",
    "InvalidQuestionConfigurationError",
    "InvalidExamConfigurationError",
    "IncompleteDataError",
    "calculate_exam_co_attainment",
    "validate_calculation_input",
]
