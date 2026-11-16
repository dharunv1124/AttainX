from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_optional_user
from app.db.models import SavedCustomExamPattern, User
from app.schemas.custom_exam_pattern import CustomExamPatternRead, CustomExamPatternWrite

router = APIRouter(prefix="/custom-exam-patterns", tags=["Custom Exam Patterns"])


@router.get("", response_model=list[CustomExamPatternRead])
def list_custom_exam_patterns(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    return db.query(SavedCustomExamPattern).order_by(
        func.lower(SavedCustomExamPattern.name), SavedCustomExamPattern.id
    ).all()


@router.post("", response_model=CustomExamPatternRead, status_code=status.HTTP_201_CREATED)
def create_custom_exam_pattern(
    payload: CustomExamPatternWrite,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    duplicate = db.query(SavedCustomExamPattern.id).filter(
        func.lower(SavedCustomExamPattern.name) == payload.name.lower()
    ).first()
    if duplicate:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A saved pattern with this name already exists.")

    pattern = SavedCustomExamPattern(
        name=payload.name,
        groups=[group.model_dump() for group in payload.groups],
    )
    db.add(pattern)
    db.commit()
    db.refresh(pattern)
    return pattern


@router.delete("/{pattern_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_custom_exam_pattern(
    pattern_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    pattern = db.query(SavedCustomExamPattern).filter(
        SavedCustomExamPattern.id == pattern_id
    ).first()
    if pattern is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved custom pattern not found.")
    db.delete(pattern)
    db.commit()