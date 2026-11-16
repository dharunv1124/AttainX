from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_optional_user
from app.db.models import User
from app.services.course_obe_report_service import CourseOBEReportService

router = APIRouter(prefix="/course-obe/subjects", tags=["Course OBE Reports"])


@router.get("/{subject_id}/report/excel")
def download_course_obe_excel_report(
    subject_id: int,
    section_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    stream, filename = CourseOBEReportService(db).generate_excel_report(subject_id, section_id)
    return Response(
        content=stream.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get("/{subject_id}/report/pdf")
def download_course_obe_pdf_report(
    subject_id: int,
    section_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    stream, filename = CourseOBEReportService(db).generate_pdf_report(subject_id, section_id)
    return Response(
        content=stream.getvalue(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )