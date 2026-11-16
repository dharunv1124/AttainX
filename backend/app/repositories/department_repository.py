"""
Department repository for database operations on departments.
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from app.db.models import Department
from app.repositories.base import BaseRepository


class DepartmentRepository(BaseRepository[Department]):
    def __init__(self, db: Session):
        super().__init__(Department, db)

    def get_by_name(self, name: str) -> Optional[Department]:
        return self.db.query(Department).filter(Department.name == name).first()

    def get_by_code(self, code: str) -> Optional[Department]:
        return self.db.query(Department).filter(Department.code == code).first()

    def create(self, name: str, code: str) -> Department:
        dept = Department(name=name.strip(), code=code.strip().upper())
        self.db.add(dept)
        self.db.commit()
        self.db.refresh(dept)
        return dept

    def update(self, department: Department, name: Optional[str] = None, code: Optional[str] = None) -> Department:
        if name is not None:
            department.name = name.strip()
        if code is not None:
            department.code = code.strip().upper()
        self.db.commit()
        self.db.refresh(department)
        return department
