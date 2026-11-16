"""
API routes package exports.
"""

from app.api.auth_routes import router as auth_router
from app.api.department_routes import router as department_router
from app.api.academic_routes import router as academic_router
from app.api.student_routes import router as student_router
from app.api.subject_routes import router as subject_router
from app.api.exam_routes import router as exam_router
from app.api.course_obe_routes import router as course_obe_router
from app.api.course_obe_attainment_routes import router as course_obe_attainment_router
from app.api.course_obe_report_routes import router as course_obe_report_router
from app.api.custom_exam_pattern_routes import router as custom_exam_pattern_router

__all__ = [
    "auth_router",
    "department_router",
    "academic_router",
    "student_router",
    "subject_router",
    "exam_router",
    "course_obe_router",
    "course_obe_attainment_router",
    "course_obe_report_router",
    "custom_exam_pattern_router",
]
