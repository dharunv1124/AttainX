from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_optional_user
from app.db.models import User
from app.repositories.course_obe_repository import CourseCOPOMappingRepository
from app.services.course_obe_context import get_course_obe_subject_for_section
from app.schemas.course_obe import (
    CO_ROW_COUNT,
    MAPPING_COLUMN_COUNT,
    CourseCOPOMappingRead,
    CourseCOPOMappingWrite,
)

router = APIRouter(prefix="/course-obe/subjects", tags=["Course OBE"])


@router.get("/{subject_id}/co-po-mapping", response_model=CourseCOPOMappingRead)
def get_course_co_po_mapping(
    subject_id: int,
    section_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    get_course_obe_subject_for_section(db, subject_id, section_id)
    mapping = CourseCOPOMappingRepository(db).get_for_context(subject_id, section_id)
    values = mapping.mapping_data if mapping else [
        [None for _ in range(MAPPING_COLUMN_COUNT)] for _ in range(CO_ROW_COUNT)
    ]
    return {"subject_id": subject_id, "section_id": section_id, "values": values}


@router.put("/{subject_id}/co-po-mapping", response_model=CourseCOPOMappingRead)
def save_course_co_po_mapping(
    subject_id: int,
    section_id: int,
    payload: CourseCOPOMappingWrite,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    get_course_obe_subject_for_section(db, subject_id, section_id)
    mapping = CourseCOPOMappingRepository(db).save_for_context(subject_id, section_id, payload.values)
    return {"subject_id": subject_id, "section_id": section_id, "values": mapping.mapping_data}