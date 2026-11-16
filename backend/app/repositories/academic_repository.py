"""
Academic structure repository for Year, Semester, and Section.
Sections are scoped by Department and Year; Semesters belong to Years.
"""

from typing import Optional, List
from sqlalchemy.orm import Session, joinedload
from app.db.models import Batch, Year, Semester, Section


class BatchRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> List[Batch]:
        return self.db.query(Batch).order_by(
            Batch.start_year != 2024,
            Batch.start_year.asc(),
            Batch.end_year.asc(),
        ).all()

    def get_by_id(self, batch_id: int) -> Optional[Batch]:
        return self.db.query(Batch).filter(Batch.id == batch_id).first()

    def get_by_name(self, batch_name: str) -> Optional[Batch]:
        return self.db.query(Batch).filter(Batch.batch_name == batch_name.strip()).first()

    def get_default(self) -> Optional[Batch]:
        return self.db.query(Batch).filter(
            Batch.start_year == 2024,
            Batch.end_year == 2028,
            Batch.is_active.is_(True),
        ).first()

    def create(self, batch_name: str, start_year: int, end_year: int, is_active: bool = True) -> Batch:
        batch = Batch(batch_name=batch_name.strip(), start_year=start_year, end_year=end_year, is_active=is_active)
        self.db.add(batch)
        self.db.commit()
        self.db.refresh(batch)
        return batch

    def has_year_range(self, start_year: int, end_year: int) -> bool:
        return self.db.query(Batch.id).filter(
            Batch.start_year == start_year,
            Batch.end_year == end_year,
        ).first() is not None

    def update(self, batch: Batch, batch_name: Optional[str] = None, start_year: Optional[int] = None, end_year: Optional[int] = None, is_active: Optional[bool] = None) -> Batch:
        if batch_name is not None:
            batch.batch_name = batch_name.strip()
        if start_year is not None:
            batch.start_year = start_year
        if end_year is not None:
            batch.end_year = end_year
        if is_active is not None:
            batch.is_active = is_active
        self.db.commit()
        self.db.refresh(batch)
        return batch


class YearRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> List[Year]:
        return self.db.query(Year).order_by(Year.year_number.asc()).all()

    def get_by_id(self, year_id: int) -> Optional[Year]:
        return self.db.query(Year).filter(Year.id == year_id).first()

    def get_by_number(self, year_number: int) -> Optional[Year]:
        return self.db.query(Year).filter(Year.year_number == year_number).first()

    def get_by_name(self, name: str) -> Optional[Year]:
        return self.db.query(Year).filter(Year.name == name).first()

    def create(self, year_number: int, name: str) -> Year:
        year = Year(year_number=year_number, name=name)
        self.db.add(year)
        self.db.commit()
        self.db.refresh(year)
        return year


class SemesterRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> List[Semester]:
        return self.db.query(Semester).order_by(Semester.semester_number.asc()).all()

    def get_by_id(self, semester_id: int) -> Optional[Semester]:
        return self.db.query(Semester).filter(Semester.id == semester_id).first()

    def get_by_number(self, semester_number: int) -> Optional[Semester]:
        return self.db.query(Semester).filter(Semester.semester_number == semester_number).first()

    def get_by_year_id(self, year_id: int) -> List[Semester]:
        return self.db.query(Semester).filter(Semester.year_id == year_id).order_by(Semester.semester_number.asc()).all()

    def create(self, semester_number: int, name: str, year_id: int) -> Semester:
        semester = Semester(semester_number=semester_number, name=name, year_id=year_id)
        self.db.add(semester)
        self.db.commit()
        self.db.refresh(semester)
        return semester


class SectionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(
        self,
        department_id: Optional[int] = None,
        year_id: Optional[int] = None,
        batch_id: Optional[int] = None,
    ) -> List[Section]:
        query = self.db.query(Section).options(
            joinedload(Section.department),
            joinedload(Section.year),
            joinedload(Section.batch),
        )
        if batch_id is not None:
            query = query.filter(Section.batch_id == batch_id)
        if department_id is not None:
            query = query.filter(Section.department_id == department_id)
        if year_id is not None:
            query = query.filter(Section.year_id == year_id)
        return query.order_by(Section.name.asc()).all()

    def get_by_id(self, section_id: int) -> Optional[Section]:
        return self.db.query(Section).options(
            joinedload(Section.department),
            joinedload(Section.year),
            joinedload(Section.batch),
        ).filter(Section.id == section_id).first()

    def get_by_unique(self, department_id: int, year_id: int, name: str, batch_id: Optional[int] = None) -> Optional[Section]:
        query = self.db.query(Section).filter(
            Section.department_id == department_id,
            Section.year_id == year_id,
            Section.name == name.strip().upper(),
        )
        if batch_id is not None:
            query = query.filter(Section.batch_id == batch_id)
        return query.first()

    def create(self, department_id: int, year_id: int, name: str, batch_id: Optional[int] = None) -> Section:
        section = Section(
            batch_id=batch_id,
            department_id=department_id,
            year_id=year_id,
            name=name.strip().upper(),
        )
        self.db.add(section)
        self.db.commit()
        self.db.refresh(section)
        return section

    def update(
        self,
        section: Section,
        name: Optional[str] = None,
        department_id: Optional[int] = None,
        year_id: Optional[int] = None,
        batch_id: Optional[int] = None,
    ) -> Section:
        if name is not None:
            section.name = name.strip().upper()
        if batch_id is not None:
            section.batch_id = batch_id
        if department_id is not None:
            section.department_id = department_id
        if year_id is not None:
            section.year_id = year_id
        self.db.commit()
        self.db.refresh(section)
        return section

    def delete(self, section_id: int) -> bool:
        section = self.get_by_id(section_id)
        if section:
            self.db.delete(section)
            self.db.commit()
            return True
        return False
