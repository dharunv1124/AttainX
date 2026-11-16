"""
Master data service managing Department, Year, Semester, and Section (Academic Hierarchy).
Department -> Year -> Semester -> Section
"""

from typing import List, Optional, Protocol
import hashlib
import json
import re
from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import (
    Batch,
    CourseCOAttainmentInputs,
    CourseCOPOMapping,
    Department,
    Exam,
    ExamCoveredCO,
    ExamQuestion,
    Section,
    Semester,
    Student,
    StudentAcademicPlacement,
    StudentMark,
    Subject,
    Year,
)
from app.repositories.department_repository import DepartmentRepository
from app.repositories.academic_repository import BatchRepository, YearRepository, SemesterRepository, SectionRepository
from app.schemas.department import DepartmentCreate, DepartmentUpdate
from app.schemas.academic import BatchUpdate, SectionCreate, SectionUpdate


class BatchCreationPayload(Protocol):
    batch_name: str
    is_active: bool


class MasterDataService:
    def __init__(self, db: Session):
        self.db = db
        self.batch_repo = BatchRepository(db)
        self.dept_repo = DepartmentRepository(db)
        self.year_repo = YearRepository(db)
        self.sem_repo = SemesterRepository(db)
        self.section_repo = SectionRepository(db)

    # ---------------- Batch Operations ----------------
    def get_default_batch(self) -> Batch:
        batch = self.batch_repo.get_default()
        if batch is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The default 2024–28 Batch is not configured or active.",
            )
        return batch

    def list_batches(self) -> List[Batch]:
        return self.batch_repo.get_all()

    def get_batch(self, batch_id: int) -> Batch:
        batch = self.batch_repo.get_by_id(batch_id)
        if not batch:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")
        return batch

    def create_batch(self, payload: BatchCreationPayload) -> Batch:
        batch_name, start_year, end_year = self._parse_batch_name(payload.batch_name)
        if self.batch_repo.get_by_name(batch_name):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Batch '{batch_name}' already exists")
        if self.batch_repo.has_year_range(start_year, end_year):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A batch already exists for this year range")
        return self.batch_repo.create(
            batch_name=batch_name,
            start_year=start_year,
            end_year=end_year,
            is_active=payload.is_active,
        )

    @staticmethod
    def _parse_batch_name(batch_name: str) -> tuple[str, int, int]:
        match = re.fullmatch(r"\s*(\d{4})\s*[-‐‑‒–—]\s*(\d{2}|\d{4})\s*", batch_name)
        if not match:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Enter batch in the format 2025–29.",
            )

        start_year = int(match.group(1))
        end_text = match.group(2)
        if len(end_text) == 2:
            end_year = (start_year // 100) * 100 + int(end_text)
            if end_year <= start_year:
                end_year += 100
        else:
            end_year = int(end_text)

        if start_year < 2000 or end_year > 2100 or end_year - start_year != 4:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Enter batch in the format 2025–29.",
            )
        return f"{start_year}–{end_year % 100:02d}", start_year, end_year

    def update_batch(self, batch_id: int, payload: BatchUpdate) -> Batch:
        batch = self.get_batch(batch_id)
        payload_name = payload.batch_name.strip() if payload.batch_name else None
        if payload_name and self.batch_repo.get_by_name(payload_name) and self.batch_repo.get_by_name(payload_name).id != batch_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Batch '{payload_name}' already exists")
        if payload.start_year is not None and payload.end_year is not None and payload.start_year > payload.end_year:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Batch start year cannot be greater than end year")
        if payload.start_year is not None and payload.end_year is None and payload.start_year > batch.end_year:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Batch start year cannot be greater than end year")
        if payload.end_year is not None and payload.start_year is None and payload.end_year < batch.start_year:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Batch start year cannot be greater than end year")
        return self.batch_repo.update(
            batch,
            batch_name=payload_name,
            start_year=payload.start_year,
            end_year=payload.end_year,
            is_active=payload.is_active,
        )

    def get_batch_deletion_status(self, batch_id: int) -> dict:
        self.get_batch(batch_id)
        if len(self.batch_repo.get_all()) <= 1:
            return {"can_delete": False, "reason": "At least one batch must remain."}
        return {"can_delete": True, "reason": None}

    def delete_batch(self, batch_id: int) -> dict:
        batch = self.get_batch(batch_id)
        remaining_batch_ids = (
            self.db.query(Batch.id)
            .with_for_update()
            .all()
        )
        if len(remaining_batch_ids) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="At least one batch must remain.",
            )
        section_ids = [
            row[0]
            for row in self.db.query(Section.id)
            .filter(Section.batch_id == batch_id)
            .all()
        ]
        student_ids = [
            row[0]
            for row in self.db.query(Student.id)
            .filter(Student.batch_id == batch_id)
            .all()
        ]
        subject_ids = [
            row[0]
            for row in self.db.query(Subject.id)
            .filter(Subject.batch_id == batch_id)
            .all()
        ]
        exam_ids = [
            row[0]
            for row in self.db.query(Exam.id)
            .filter(
                or_(
                    Exam.batch_id == batch_id,
                    Exam.section_id.in_(section_ids),
                )
            )
            .all()
        ]
        batch_name = batch.batch_name
        self._ensure_batch_delete_isolated(
            batch_id=batch_id,
            section_ids=section_ids,
            student_ids=student_ids,
            subject_ids=subject_ids,
            exam_ids=exam_ids,
        )

        try:
            self._delete_owned_records(
                section_ids=section_ids,
                student_ids=student_ids,
                subject_ids=subject_ids,
                exam_ids=exam_ids,
                batch_id=batch_id,
                delete_batch=True,
                batch=batch,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {"deleted_id": batch_id, "message": f"Batch '{batch_name}' permanently deleted."}

    def delete_section(
        self,
        section_id: int,
        expected_plan_token: str,
    ) -> dict:
        section = self.db.query(Section).filter(
            Section.id == section_id
        ).with_for_update().first()
        if section is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Section not found",
            )
        preliminary_plan = self._build_section_deletion_plan(section)
        candidate_student_ids = (
            preliminary_plan["student_ids_to_delete"]
            + preliminary_plan["student_ids_preserved"]
        )
        if candidate_student_ids:
            self.db.query(Student.id).filter(
                Student.id.in_(candidate_student_ids)
            ).with_for_update().all()
        if preliminary_plan["exam_ids"]:
            self.db.query(Exam.id).filter(
                Exam.id.in_(preliminary_plan["exam_ids"])
            ).with_for_update().all()

        # Lock owners so dependent inserts cannot race the confirmed deletion plan.
        plan = self._build_section_deletion_plan(section)
        if expected_plan_token != plan["plan_token"]:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Section data changed after the deletion preview. Review the updated counts and confirm again.",
            )
        section_name = section.name

        try:
            self.db.query(Student).filter(
                Student.section_id == section.id,
                Student.id.notin_(plan["student_ids_to_delete"]),
            ).update(
                {Student.section_id: None},
                synchronize_session=False,
            )
            self._delete_owned_records(
                section_ids=[section.id],
                student_ids=plan["student_ids_to_delete"],
                subject_ids=[],
                exam_ids=plan["exam_ids"],
                batch_id=None,
                delete_batch=False,
                section=section,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {"deleted_id": section_id, "message": f"Section '{section_name}' permanently deleted."}

    def _ensure_batch_delete_isolated(
        self,
        *,
        batch_id: int,
        section_ids: List[int],
        student_ids: List[int],
        subject_ids: List[int],
        exam_ids: List[int],
    ) -> None:
        cross_batch_section_exam = (
            self.db.query(Exam.id)
            .join(Section, Exam.section_id == Section.id)
            .filter(Section.batch_id == batch_id, Exam.batch_id != batch_id)
            .first()
        )
        external_subject_exam = (
            self.db.query(Exam.id)
            .filter(Exam.subject_id.in_(subject_ids), Exam.batch_id != batch_id)
            .first()
            if subject_ids
            else None
        )
        external_subject_course_data = (
            self.db.query(CourseCOPOMapping.id)
            .join(Section, CourseCOPOMapping.section_id == Section.id)
            .filter(
                CourseCOPOMapping.subject_id.in_(subject_ids),
                Section.batch_id != batch_id,
            )
            .first()
            if subject_ids
            else None
        )
        external_subject_attainment_data = (
            self.db.query(CourseCOAttainmentInputs.id)
            .join(Section, CourseCOAttainmentInputs.section_id == Section.id)
            .filter(
                CourseCOAttainmentInputs.subject_id.in_(subject_ids),
                Section.batch_id != batch_id,
            )
            .first()
            if subject_ids
            else None
        )
        external_section_course_data = (
            self.db.query(CourseCOPOMapping.id)
            .join(Section, CourseCOPOMapping.section_id == Section.id)
            .join(Subject, CourseCOPOMapping.subject_id == Subject.id)
            .filter(
                CourseCOPOMapping.section_id.in_(section_ids),
                Section.batch_id == batch_id,
                Subject.batch_id != batch_id,
            )
            .first()
            if section_ids
            else None
        )
        external_section_attainment_data = (
            self.db.query(CourseCOAttainmentInputs.id)
            .join(Section, CourseCOAttainmentInputs.section_id == Section.id)
            .join(Subject, CourseCOAttainmentInputs.subject_id == Subject.id)
            .filter(
                CourseCOAttainmentInputs.section_id.in_(section_ids),
                Section.batch_id == batch_id,
                Subject.batch_id != batch_id,
            )
            .first()
            if section_ids
            else None
        )
        external_student_marks = (
            self.db.query(StudentMark.id)
            .join(Exam, StudentMark.exam_id == Exam.id)
            .join(Student, StudentMark.student_id == Student.id)
            .filter(
                or_(
                    (Exam.id.in_(exam_ids) & (Student.batch_id != batch_id)),
                    (Student.id.in_(student_ids) & (Exam.batch_id != batch_id)),
                )
            )
            .first()
            if exam_ids or student_ids
            else None
        )
        cross_batch_student = (
            self.db.query(Student.id)
            .filter(
                Student.section_id.in_(section_ids),
                Student.batch_id != batch_id,
            )
            .first()
            if section_ids
            else None
        )
        cross_batch_placement = (
            self.db.query(StudentAcademicPlacement.id)
            .filter(
                or_(
                    (
                        StudentAcademicPlacement.section_id.in_(section_ids)
                        & (StudentAcademicPlacement.batch_id != batch_id)
                    ),
                    (
                        StudentAcademicPlacement.student_id.in_(student_ids)
                        & (StudentAcademicPlacement.batch_id != batch_id)
                    ),
                )
            )
            .first()
            if section_ids or student_ids
            else None
        )
        if any((
            cross_batch_section_exam,
            external_subject_exam,
            external_subject_course_data,
            external_subject_attainment_data,
            external_section_course_data,
            external_section_attainment_data,
            external_student_marks,
            cross_batch_student,
            cross_batch_placement,
        )):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Batch deletion was stopped because related records reference another batch. Resolve the cross-batch data conflict first.",
            )

    def _delete_owned_records(
        self,
        *,
        section_ids: List[int],
        student_ids: List[int],
        subject_ids: List[int],
        exam_ids: List[int],
        batch_id: Optional[int],
        delete_batch: bool,
        batch: Optional[Batch] = None,
        section: Optional[Section] = None,
    ) -> None:
        if section_ids or subject_ids:
            self.db.query(CourseCOPOMapping).filter(
                or_(
                    CourseCOPOMapping.section_id.in_(section_ids),
                    CourseCOPOMapping.subject_id.in_(subject_ids),
                )
            ).delete(synchronize_session=False)
            self.db.query(CourseCOAttainmentInputs).filter(
                or_(
                    CourseCOAttainmentInputs.section_id.in_(section_ids),
                    CourseCOAttainmentInputs.subject_id.in_(subject_ids),
                )
            ).delete(synchronize_session=False)

        if exam_ids or student_ids:
            self.db.query(StudentMark).filter(
                or_(
                    StudentMark.exam_id.in_(exam_ids),
                    StudentMark.student_id.in_(student_ids),
                )
            ).delete(synchronize_session=False)

        if exam_ids:
            self.db.query(ExamQuestion).filter(ExamQuestion.exam_id.in_(exam_ids)).delete(
                synchronize_session=False
            )
            self.db.query(ExamCoveredCO).filter(ExamCoveredCO.exam_id.in_(exam_ids)).delete(
                synchronize_session=False
            )
            self.db.query(Exam).filter(Exam.id.in_(exam_ids)).delete(synchronize_session=False)

        placement_query = self.db.query(StudentAcademicPlacement)
        if delete_batch:
            placement_query = placement_query.filter(
                or_(
                    StudentAcademicPlacement.batch_id == batch_id,
                    StudentAcademicPlacement.section_id.in_(section_ids),
                    StudentAcademicPlacement.student_id.in_(student_ids),
                )
            )
        elif section_ids:
            placement_query = placement_query.filter(
                or_(
                    StudentAcademicPlacement.section_id.in_(section_ids),
                    StudentAcademicPlacement.student_id.in_(student_ids),
                )
            )
        placement_query.delete(synchronize_session=False)

        if student_ids:
            self.db.query(Student).filter(Student.id.in_(student_ids)).delete(
                synchronize_session=False
            )
        if section_ids and section is None:
            self.db.query(Section).filter(Section.id.in_(section_ids)).delete(
                synchronize_session=False
            )
        if subject_ids:
            self.db.query(Subject).filter(Subject.id.in_(subject_ids)).delete(
                synchronize_session=False
            )
        if delete_batch and batch is not None:
            self.db.delete(batch)
        if not delete_batch and section is not None:
            self.db.delete(section)

    # ---------------- Department Operations ----------------
    def list_departments(self, skip: int = 0, limit: int = 100) -> List[Department]:
        return self.dept_repo.get_all(skip=skip, limit=limit)

    def get_department(self, dept_id: int) -> Department:
        dept = self.dept_repo.get(dept_id)
        if not dept:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
        return dept

    def create_department(self, payload: DepartmentCreate) -> Department:
        name = payload.name.strip()
        code = payload.code.strip().upper()
        if self.dept_repo.get_by_name(name):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Department with name '{name}' already exists")
        if self.dept_repo.get_by_code(code):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Department with code '{code}' already exists")
        return self.dept_repo.create(name=name, code=code)

    def update_department(self, dept_id: int, payload: DepartmentUpdate) -> Department:
        dept = self.get_department(dept_id)
        if payload.name:
            existing = self.dept_repo.get_by_name(payload.name.strip())
            if existing and existing.id != dept_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Department with name '{payload.name}' already exists")
        if payload.code:
            existing = self.dept_repo.get_by_code(payload.code.strip().upper())
            if existing and existing.id != dept_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Department with code '{payload.code}' already exists")
        return self.dept_repo.update(department=dept, name=payload.name, code=payload.code)

    def delete_department(self, dept_id: int) -> bool:
        dept = self.get_department(dept_id)
        return self.dept_repo.delete(dept.id)

    # ---------------- Year & Semester Operations ----------------
    def list_years(self) -> List[Year]:
        return self.year_repo.get_all()

    def get_year(self, year_id: int) -> Year:
        year = self.year_repo.get_by_id(year_id)
        if not year:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Year not found")
        return year

    def list_semesters(self, year_id: Optional[int] = None) -> List[Semester]:
        if year_id is not None:
            return self.sem_repo.get_by_year_id(year_id)
        return self.sem_repo.get_all()

    def get_semester(self, sem_id: int) -> Semester:
        sem = self.sem_repo.get_by_id(sem_id)
        if not sem:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Semester not found")
        return sem

    # ---------------- Section Operations ----------------
    def list_sections(
        self,
        department_id: Optional[int] = None,
        year_id: Optional[int] = None,
        batch_id: Optional[int] = None,
    ) -> List[Section]:
        if batch_id is None:
            batch_id = self.get_default_batch().id
        return self.section_repo.get_all(
            department_id=department_id,
            year_id=year_id,
            batch_id=batch_id,
        )

    def get_section(self, section_id: int) -> Section:
        section = self.section_repo.get_by_id(section_id)
        if not section:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
        return section

    def create_section(self, payload: SectionCreate) -> Section:
        # Validate existence of foreign entities.
        self.get_department(payload.department_id)
        self.get_year(payload.year_id)
        batch_id = payload.batch_id or self.get_default_batch().id
        self.get_batch(batch_id)

        name = payload.name.strip().upper()
        if self.section_repo.get_by_unique(payload.department_id, payload.year_id, name, batch_id=batch_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Section '{name}' already exists for this Batch, Department, and Year",
            )

        return self.section_repo.create(
            batch_id=batch_id,
            department_id=payload.department_id,
            year_id=payload.year_id,
            name=name,
        )

    def update_section(self, section_id: int, payload: SectionUpdate) -> Section:
        section = self.get_section(section_id)
        batch_id = payload.batch_id or section.batch_id or self.get_default_batch().id
        dept_id = payload.department_id or section.department_id
        year_id = payload.year_id or section.year_id
        name = (payload.name or section.name).strip().upper()

        if payload.department_id:
            self.get_department(dept_id)
        if payload.year_id:
            self.get_year(year_id)
        if payload.batch_id or section.batch_id is None:
            self.get_batch(batch_id)
        existing = self.section_repo.get_by_unique(dept_id, year_id, name, batch_id=batch_id)
        if existing and existing.id != section_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Section '{name}' already exists for this Batch, Department, and Year",
            )

        return self.section_repo.update(
            section=section,
            name=name,
            batch_id=batch_id,
            department_id=dept_id,
            year_id=year_id,
        )

    def _build_section_deletion_plan(self, section: Section) -> dict:
        section_id = section.id
        candidate_student_ids = {
            row[0]
            for row in self.db.query(Student.id)
            .filter(Student.section_id == section_id)
            .all()
        }
        candidate_student_ids.update(
            row[0]
            for row in self.db.query(StudentAcademicPlacement.student_id)
            .filter(
                StudentAcademicPlacement.section_id == section_id,
                StudentAcademicPlacement.is_current.is_(True),
            )
            .all()
        )

        protected_student_ids = set()
        if candidate_student_ids:
            protected_student_ids.update(
                row[0]
                for row in self.db.query(Student.id)
                .filter(
                    Student.id.in_(candidate_student_ids),
                    Student.section_id.isnot(None),
                    Student.section_id != section_id,
                )
                .all()
            )
            protected_student_ids.update(
                row[0]
                for row in self.db.query(StudentAcademicPlacement.student_id)
                .filter(
                    StudentAcademicPlacement.student_id.in_(candidate_student_ids),
                    StudentAcademicPlacement.is_current.is_(True),
                    StudentAcademicPlacement.section_id.isnot(None),
                    StudentAcademicPlacement.section_id != section_id,
                )
                .all()
            )

        student_ids = sorted(candidate_student_ids - protected_student_ids)
        exam_ids = sorted(
            row[0]
            for row in self.db.query(Exam.id)
            .filter(Exam.section_id == section_id)
            .all()
        )

        placement_filters = [StudentAcademicPlacement.section_id == section_id]
        if student_ids:
            placement_filters.append(
                StudentAcademicPlacement.student_id.in_(student_ids)
            )
        placement_ids = sorted(
            row[0]
            for row in self.db.query(StudentAcademicPlacement.id)
            .filter(or_(*placement_filters))
            .all()
        )

        mark_filters = []
        if exam_ids:
            mark_filters.append(StudentMark.exam_id.in_(exam_ids))
        if student_ids:
            mark_filters.append(StudentMark.student_id.in_(student_ids))
        mark_ids = sorted(
            row[0]
            for row in (
                self.db.query(StudentMark.id).filter(or_(*mark_filters)).all()
                if mark_filters
                else []
            )
        )

        question_ids = sorted(
            row[0]
            for row in self.db.query(ExamQuestion.id)
            .filter(ExamQuestion.exam_id.in_(exam_ids))
            .all()
        ) if exam_ids else []
        covered_co_ids = sorted(
            row[0]
            for row in self.db.query(ExamCoveredCO.id)
            .filter(ExamCoveredCO.exam_id.in_(exam_ids))
            .all()
        ) if exam_ids else []
        mapping_ids = sorted(
            row[0]
            for row in self.db.query(CourseCOPOMapping.id)
            .filter(CourseCOPOMapping.section_id == section_id)
            .all()
        )
        attainment_input_ids = sorted(
            row[0]
            for row in self.db.query(CourseCOAttainmentInputs.id)
            .filter(CourseCOAttainmentInputs.section_id == section_id)
            .all()
        )

        deletion_evidence = {
            "section_id": section_id,
            "student_ids": student_ids,
            "protected_student_ids": sorted(candidate_student_ids & protected_student_ids),
            "placement_ids": placement_ids,
            "mark_ids": mark_ids,
            "exam_ids": exam_ids,
            "question_ids": question_ids,
            "covered_co_ids": covered_co_ids,
            "mapping_ids": mapping_ids,
            "attainment_input_ids": attainment_input_ids,
        }
        plan_token = hashlib.sha256(
            json.dumps(
                deletion_evidence,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        return {
            "student_ids_to_delete": student_ids,
            "student_ids_preserved": sorted(candidate_student_ids & protected_student_ids),
            "exam_ids": exam_ids,
            "student_count": len(student_ids),
            "placement_count": len(placement_ids),
            "student_mark_count": len(mark_ids),
            "exam_count": len(exam_ids),
            "exam_question_count": len(question_ids),
            "exam_covered_co_count": len(covered_co_ids),
            "course_co_po_mapping_count": len(mapping_ids),
            "course_co_attainment_input_count": len(attainment_input_ids),
            "plan_token": plan_token,
        }

    def get_section_deletion_status(self, section_id: int) -> dict:
        section = self.get_section(section_id)
        plan = self._build_section_deletion_plan(section)
        return {
            "can_delete": True,
            "reason": None,
            **plan,
        }
