"""
FastAPI application entry point for Phase 4: Foundational Master Data & Authentication.
Strictly limited to confirmed Phase 4 scope.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    auth_router,
    department_router,
    academic_router,
    student_router,
    subject_router,
    exam_router,
    course_obe_router,
    course_obe_attainment_router,
    course_obe_report_router,
    custom_exam_pattern_router,
)
from app.config import settings
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.db.models import User
from app.seeds.dev_seed import seed_database

# Production schema is strictly managed by Alembic migrations (alembic upgrade head).
# Base.metadata.create_all and development seed data are strictly isolated from production.
if settings.ENVIRONMENT in ("development", "testing"):
    Base.metadata.create_all(bind=engine)
    if settings.ENVIRONMENT == "development":
        with SessionLocal() as _db:
            if not _db.query(User).first():
                seed_database(_db)

app = FastAPI(
    title="OBE Course Outcome Attainment System - Exam Configuration API",
    description="FastAPI backend providing Master Data, Exam Configuration, and Phase 6 Marks Entry.",
    version="0.6.0",
)

# CORS origins are explicitly configured for the deployed frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(auth_router, prefix="/api")
app.include_router(department_router, prefix="/api")
app.include_router(academic_router, prefix="/api")
app.include_router(student_router, prefix="/api")
app.include_router(subject_router, prefix="/api")
app.include_router(exam_router, prefix="/api")
app.include_router(course_obe_router, prefix="/api")
app.include_router(course_obe_attainment_router, prefix="/api")
app.include_router(course_obe_report_router, prefix="/api")
app.include_router(custom_exam_pattern_router, prefix="/api")


@app.get("/api/health", tags=["Health"])
def health_check():
    """System health check endpoint."""
    return {"status": "ok", "phase": 5, "database": engine.dialect.name}
