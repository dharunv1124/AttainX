"""
Repositories package exports.
"""

from app.repositories.base import BaseRepository
from app.repositories.user_repository import UserRepository
from app.repositories.department_repository import DepartmentRepository
from app.repositories.academic_repository import YearRepository, SemesterRepository, SectionRepository
from app.repositories.student_repository import StudentRepository
from app.repositories.subject_repository import SubjectRepository
from app.repositories.exam_repository import ExamRepository

__all__ = [
    "BaseRepository",
    "UserRepository",
    "DepartmentRepository",
    "YearRepository",
    "SemesterRepository",
    "SectionRepository",
    "StudentRepository",
    "SubjectRepository",
    "ExamRepository",
]
