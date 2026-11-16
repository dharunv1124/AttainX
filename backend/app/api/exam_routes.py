"""
Exam Configuration and Workspace API routes.
Faculty workflow:
Class Selection -> Subject Selection -> Exam Details -> Covered COs -> Pass Percentage -> Question Configuration.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, status, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_optional_user
from app.db.models import User
from app.schemas.exam import ExamCreate, ExamUpdate, ExamDetailRead
from app.schemas.marks import MarksSaveRequest
from app.services.exam_service import ExamService
from app.services.marks_service import MarksApiService
from app.services.report_service import ExamReportService

router = APIRouter(prefix="/exams", tags=["Exam Configuration"])


@router.get("", response_model=List[ExamDetailRead])
def list_exams(
    department_id: Optional[int] = None,
    year_id: Optional[int] = None,
    semester_id: Optional[int] = None,
    section_id: Optional[int] = None,
    subject_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """
    List configured exams, optionally filtered by batch, class cohort, and subject.
    Allows faculty to view and open existing exams.
    """
    return ExamService(db).list_exams(
        department_id=department_id,
        year_id=year_id,
        semester_id=semester_id,
        section_id=section_id,
        subject_id=subject_id,
        batch_id=batch_id,
    )


@router.post("", response_model=ExamDetailRead, status_code=status.HTTP_201_CREATED)
def create_exam(
    payload: ExamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """
    Create a new exam with validated question configuration and covered COs.
    Tied to the selected class (Department -> Year -> Semester -> Section) and subject.
    """
    return ExamService(db).create_exam(payload)


@router.get("/{exam_id}", response_model=ExamDetailRead)
def get_exam(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """
    Retrieve full exam configuration for the Exam Workspace:
    Includes Class Cohort, Subject, Covered COs, Pass Percentage, and Question Details.
    """
    return ExamService(db).get_exam(exam_id)


@router.put("/{exam_id}", response_model=ExamDetailRead)
def update_exam(
    exam_id: int,
    payload: ExamUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Update exam details, covered COs, pass percentage, or question configuration."""
    return ExamService(db).update_exam(exam_id, payload)


@router.delete("/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exam(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """Delete an exam."""
    ExamService(db).delete_exam(exam_id)


# --- Phase 6 Marks Entry and CO Attainment Endpoints ---

@router.get("/{exam_id}/roster")
def get_exam_roster(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """
    1. Load the students belonging to the exam's selected Department -> Year -> Semester -> Section.
    """
    return MarksApiService(db).get_exam_roster(exam_id)


@router.get("/{exam_id}/questions")
def get_exam_questions(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """
    2. Load the questions configured for that exam in question-number order.
    """
    return MarksApiService(db).get_exam_questions(exam_id)


@router.get("/{exam_id}/marks")
def get_exam_marks(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """
    Load saved marks and calculated CO results.
    """
    return MarksApiService(db).get_saved_marks_and_results(exam_id)


@router.post("/{exam_id}/marks")
def save_exam_marks(
    exam_id: int,
    payload: MarksSaveRequest,
    require_complete: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """
    Save and edit marks, validate cohort consistency, validate mark bounds,
    and recalculate CO results using the Phase 3 domain engine.
    """
    submitted_marks = [
        m.model_dump() if hasattr(m, "model_dump") else m.dict()
        for m in payload.marks
    ]
    return MarksApiService(db).save_marks_and_calculate(
        exam_id=exam_id,
        submitted_marks=submitted_marks,
        require_complete=require_complete,
    )


@router.get("/{exam_id}/report/excel")
def download_excel_report(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """
    Generate and download an authoritative Excel (.xlsx) report for an exam.
    Contains exam metadata and student question-wise marks with calculated CO attainment results.
    """
    service = ExamReportService(db)
    stream, filename = service.generate_excel_report(exam_id)
    return Response(
        content=stream.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get("/{exam_id}/report/pdf")
def download_pdf_report(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """
    Generate and download a clean, printable PDF (.pdf) report for an exam.
    Contains exam metadata and student question-wise marks with calculated CO attainment results.
    """
    service = ExamReportService(db)
    stream, filename = service.generate_pdf_report(exam_id)
    return Response(
        content=stream.getvalue(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
