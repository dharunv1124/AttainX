from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_optional_user
from app.db.models import User
from app.domain.course_obe_attainment import (
    calculate_course_overall_co_attainment,
    calculate_course_po_attainment,
    calculate_course_po_attainment_overall,
)
from app.repositories.course_obe_attainment_repository import CourseCOAttainmentRepository
from app.repositories.course_obe_repository import CourseCOPOMappingRepository
from app.services.course_obe_context import get_course_obe_subject_for_section
from app.schemas.course_obe_attainment import (
    CourseCOAttainmentInputRow,
    CourseCOAttainmentRead,
    CourseCOAttainmentWrite,
    CoursePOAttainmentRead,
)
from app.schemas.course_obe import CO_ROW_COUNT, MAPPING_COLUMN_COUNT

router = APIRouter(prefix="/course-obe/subjects", tags=["Course OBE"])


def _empty_inputs() -> list[dict[str, None]]:
    return [
        {"a": None, "b": None, "c": None, "university": None, "g": None}
        for _ in range(5)
    ]


def _response(subject_id: int, section_id: int, inputs: list[dict]) -> CourseCOAttainmentRead:
    return CourseCOAttainmentRead(
        subject_id=subject_id,
        section_id=section_id,
        inputs=inputs,
        results=calculate_course_overall_co_attainment(inputs),
    )


@router.get("/{subject_id}/overall-co-attainment", response_model=CourseCOAttainmentRead)
def get_course_overall_co_attainment(
    subject_id: int,
    section_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    get_course_obe_subject_for_section(db, subject_id, section_id)
    record = CourseCOAttainmentRepository(db).get_for_context(subject_id, section_id)
    inputs = record.input_data if record else _empty_inputs()
    return _response(subject_id, section_id, inputs)


@router.put("/{subject_id}/overall-co-attainment", response_model=CourseCOAttainmentRead)
def save_course_overall_co_attainment(
    subject_id: int,
    section_id: int,
    payload: CourseCOAttainmentWrite,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    get_course_obe_subject_for_section(db, subject_id, section_id)
    inputs = [row.model_dump() for row in payload.inputs]
    record = CourseCOAttainmentRepository(db).save_for_context(subject_id, section_id, inputs)
    return _response(subject_id, section_id, record.input_data)


@router.get("/{subject_id}/po-attainment", response_model=CoursePOAttainmentRead)
def get_course_po_attainment(
    subject_id: int,
    section_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    get_course_obe_subject_for_section(db, subject_id, section_id)
    mapping_record = CourseCOPOMappingRepository(db).get_for_context(subject_id, section_id)
    mappings = mapping_record.mapping_data if mapping_record else [
        [None for _ in range(MAPPING_COLUMN_COUNT)] for _ in range(CO_ROW_COUNT)
    ]
    attainment_record = CourseCOAttainmentRepository(db).get_for_context(subject_id, section_id)
    inputs = attainment_record.input_data if attainment_record else _empty_inputs()
    overall_results = calculate_course_overall_co_attainment(inputs)
    values = calculate_course_po_attainment(mappings, overall_results)
    return {
        "subject_id": subject_id,
        "section_id": section_id,
        "values": values,
        "overall_values": calculate_course_po_attainment_overall(values),
    }