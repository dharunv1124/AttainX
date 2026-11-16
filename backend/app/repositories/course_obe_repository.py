from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import CourseCOPOMapping


class CourseCOPOMappingRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_for_context(self, subject_id: int, section_id: int) -> Optional[CourseCOPOMapping]:
        return (
            self.db.query(CourseCOPOMapping)
            .filter(
                CourseCOPOMapping.subject_id == subject_id,
                CourseCOPOMapping.section_id == section_id,
            )
            .first()
        )

    def save_for_context(
        self,
        subject_id: int,
        section_id: int,
        values: list[list[int | None]],
    ) -> CourseCOPOMapping:
        mapping = self.get_for_context(subject_id, section_id)
        if mapping is None:
            mapping = CourseCOPOMapping(subject_id=subject_id, section_id=section_id, mapping_data=values)
            self.db.add(mapping)
        else:
            mapping.mapping_data = values

        self.db.commit()
        self.db.refresh(mapping)
        return mapping