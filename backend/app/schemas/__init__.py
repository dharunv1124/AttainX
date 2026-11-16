"""
Schemas package exports.
"""

from app.schemas.auth import LoginRequest, TokenResponse, TokenPayload
from app.schemas.user import UserCreate, UserUpdate, UserRead
from app.schemas.department import DepartmentCreate, DepartmentUpdate, DepartmentRead
from app.schemas.academic import (
    YearRead,
    SemesterRead,
    SectionCreate,
    SectionUpdate,
    SectionRead,
    SectionDetailRead,
)
from app.schemas.student import StudentCreate, StudentUpdate, StudentRead, StudentDetailRead
from app.schemas.subject import SubjectCreate, SubjectUpdate, SubjectRead
from app.schemas.exam import ExamQuestionConfig, ExamCreate, ExamUpdate, ExamRead, ExamDetailRead

__all__ = [
    "LoginRequest",
    "TokenResponse",
    "TokenPayload",
    "UserCreate",
    "UserUpdate",
    "UserRead",
    "DepartmentCreate",
    "DepartmentUpdate",
    "DepartmentRead",
    "YearRead",
    "SemesterRead",
    "SectionCreate",
    "SectionUpdate",
    "SectionRead",
    "SectionDetailRead",
    "StudentCreate",
    "StudentUpdate",
    "StudentRead",
    "StudentDetailRead",
    "SubjectCreate",
    "SubjectUpdate",
    "SubjectRead",
    "ExamQuestionConfig",
    "ExamCreate",
    "ExamUpdate",
    "ExamRead",
    "ExamDetailRead",
]
