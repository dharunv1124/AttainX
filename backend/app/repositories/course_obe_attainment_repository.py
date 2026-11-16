from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import CourseCOAttainmentInputs


class CourseCOAttainmentRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_for_context(self, subject_id: int, section_id: int) -> Optional[CourseCOAttainmentInputs]:
        return (
            self.db.query(CourseCOAttainmentInputs)
            .filter(
                CourseCOAttainmentInputs.subject_id == subject_id,
                CourseCOAttainmentInputs.section_id == section_id,
            )
            .first()
        )

    def save_for_context(
        self,
        subject_id: int,
        section_id: int,
        inputs: list[dict[str, int | float | None]],
    ) -> CourseCOAttainmentInputs:
        record = self.get_for_context(subject_id, section_id)
        if record is None:
            record = CourseCOAttainmentInputs(
                subject_id=subject_id,
                section_id=section_id,
                input_data=inputs,
            )
            self.db.add(record)
        else:
            record.input_data = inputs

        self.db.commit()
        self.db.refresh(record)
        return record