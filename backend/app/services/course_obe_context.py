from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import Section, Subject


def get_course_obe_subject_for_section(db: Session, subject_id: int, section_id: int) -> Subject:
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if subject is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")

    section = db.query(Section).filter(Section.id == section_id).first()
    if section is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found.")

    if (
        section.batch_id != subject.batch_id
        or (
            subject.department_id is not None
            and (
                section.department_id != subject.department_id
                or section.year_id != subject.year_id
            )
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Section does not belong to the selected subject's Department and Year.",
        )

    return subject