"""
Student service managing student records.
Students belong strictly to a class/section (never to a subject).
Supports cohort retrieval by section and hierarchy filters.
"""

import csv
import unicodedata
from io import BytesIO, StringIO
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException, UploadFile, status
from openpyxl import load_workbook
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Semester, Student
from app.repositories.student_repository import StudentRepository
from app.repositories.academic_repository import SectionRepository
from app.schemas.student import StudentCreate, StudentPlacementUpdate, StudentUpdate


REQUIRED_IMPORT_COLUMNS = ["Register Number", "Student Name"]


class StudentService:
    def __init__(self, db: Session):
        self.db = db
        self.student_repo = StudentRepository(db)
        self.section_repo = SectionRepository(db)

    def get_student(self, student_id: int) -> Student:
        student = self.student_repo.get_by_id_with_details(student_id)
        if not student:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
        return student

    def get_by_register_no(self, register_no: str, batch_id: int) -> Student:
        student = self.student_repo.get_by_register_no(register_no, batch_id=batch_id)
        if not student:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
        return student

    def _normalise_header(self, value: Any) -> str:
        if value is None:
            return ""
        hidden_whitespace = str(value).translate(str.maketrans("", "", "\ufeff\u200b\u200c\u200d\u2060"))
        return "".join(hidden_whitespace.casefold().split())

    def _normalise_student_name(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        return "".join(
            character
            for character in normalized
            if not character.isspace() and not unicodedata.category(character).startswith("P")
        )

    def _has_required_import_headers(self, headers: List[str]) -> bool:
        normalized_headers = {self._normalise_header(header) for header in headers}
        return all(self._normalise_header(column) in normalized_headers for column in REQUIRED_IMPORT_COLUMNS)

    def _rows_to_import_dicts(
        self,
        headers: List[str],
        source_rows: Iterable[Iterable[Any]],
    ) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        for source_row in source_rows:
            values = list(source_row)
            if not any(value is not None and str(value).strip() for value in values):
                continue
            rows.append({
                header: "" if index >= len(values) or values[index] is None else str(values[index]).strip()
                for index, header in enumerate(headers)
            })
        return rows

    def _missing_import_headers_error(self) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required columns: Register Number, Student Name.",
        )

    def _parse_student_import_file(self, uploaded_file: UploadFile) -> Tuple[List[Dict[str, str]], str]:
        if uploaded_file.filename is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is missing a filename.")

        filename = uploaded_file.filename.lower()
        file_bytes = uploaded_file.file.read()
        uploaded_file.file.seek(0)

        if filename.endswith(".csv"):
            text = file_bytes.decode("utf-8-sig")
            csv_rows = list(csv.reader(StringIO(text)))
            first_nonblank = next(
                (index for index, row in enumerate(csv_rows) if any(value.strip() for value in row)),
                None,
            )
            if first_nonblank is None:
                raise self._missing_import_headers_error()

            headers = [value.strip() for value in csv_rows[first_nonblank]]
            if not self._has_required_import_headers(headers):
                raise self._missing_import_headers_error()
            return self._rows_to_import_dicts(headers, csv_rows[first_nonblank + 1:]), "csv"

        if filename.endswith(".xlsx"):
            workbook = load_workbook(filename=BytesIO(file_bytes), read_only=True, data_only=True)
            parsed_rows: Optional[List[Dict[str, str]]] = None
            for sheet in workbook.worksheets:
                sheet_rows = iter(sheet.iter_rows(values_only=True))
                for row in sheet_rows:
                    candidate = ["" if value is None else str(value).strip() for value in row]
                    if self._has_required_import_headers(candidate):
                        parsed_rows = self._rows_to_import_dicts(candidate, sheet_rows)
                        break
                if parsed_rows is not None:
                    break

            workbook.close()
            if parsed_rows is None:
                raise self._missing_import_headers_error()

            return parsed_rows, "xlsx"

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Please upload a CSV or XLSX file.",
        )

    def _validate_section_semester(self, section: Any, semester_id: Optional[int]) -> None:
        if semester_id is None:
            return
        semester = self.db.query(Semester).filter(Semester.id == semester_id).first()
        if semester is None or semester.year_id != section.year_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Semester must belong to the selected section's Year.",
            )

    def _validate_student_import_rows(
        self,
        section_id: int,
        rows: List[Dict[str, str]],
        semester_id: Optional[int] = None,
        lock_existing: bool = False,
    ) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
        section = self.section_repo.get_by_id(section_id)
        if not section:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Selected section does not exist.")
        if section.batch_id is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Selected section has no Batch context.")
        self._validate_section_semester(section, semester_id)

        if not rows:
            return {
                "section_id": section_id,
                "batch_id": section.batch_id,
                "total_rows": 0,
                "valid_rows": 0,
                "invalid_rows": 0,
                "new_students": 0,
                "already_assigned": 0,
                "eligible_for_restoration": 0,
                "placement_conflicts": 0,
                "duplicate_register_numbers": [],
                "identity_resolutions": [],
                "errors": ["The uploaded file is empty or contains no readable rows."],
            }, []

        header_map = {self._normalise_header(key): key for key in rows[0].keys() if key is not None}
        missing_columns = [
            column for column in REQUIRED_IMPORT_COLUMNS
            if self._normalise_header(column) not in header_map
        ]
        if missing_columns:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required columns: {', '.join(missing_columns)}. Required columns are: Register Number, Student Name.",
            )

        errors: List[str] = []
        duplicate_register_numbers: set[str] = set()
        classified_students: List[Dict[str, Any]] = []
        identity_resolutions: List[Dict[str, Any]] = []
        invalid_rows: set[int] = set()
        placement_conflicts = 0
        new_students = 0
        already_assigned = 0
        eligible_for_restoration = 0
        rows_total = len(rows)

        occurrences: Dict[str, List[int]] = {}
        for row_index, row in enumerate(rows, start=1):
            row_values = {key: (value or "").strip() for key, value in row.items()}
            if not any(value for value in row_values.values()):
                continue

            register_key = header_map[self._normalise_header("Register Number")]
            name_key = header_map[self._normalise_header("Student Name")]
            register_value = (row_values.get(register_key) or "").strip()
            name_value = (row_values.get(name_key) or "").strip()

            if not register_value:
                errors.append(f"Row {row_index}: Register Number is required.")
                invalid_rows.add(row_index)
                continue

            if not name_value:
                errors.append(f"Row {row_index}: Student Name is required.")
                invalid_rows.add(row_index)
                continue

            if len(register_value) > 50:
                errors.append(f"Row {row_index}: Register Number must be 50 characters or fewer.")
                invalid_rows.add(row_index)
                continue

            if len(name_value) < 2 or len(name_value) > 100:
                errors.append(f"Row {row_index}: Student Name must be between 2 and 100 characters.")
                invalid_rows.add(row_index)
                continue

            register_no = register_value.upper()
            occurrences.setdefault(register_no, []).append(row_index)

        for register_no, row_numbers in occurrences.items():
            if len(row_numbers) > 1:
                duplicate_register_numbers.add(register_no)
                for row_number in row_numbers:
                    invalid_rows.add(row_number)
                    errors.append(f"Row {row_number}: Duplicate register number '{register_no}' found within the uploaded file.")

        for row_index, row in enumerate(rows, start=1):
            row_values = {key: (value or "").strip() for key, value in row.items()}
            if not any(value for value in row_values.values()):
                continue

            if row_index in invalid_rows:
                continue

            register_key = header_map[self._normalise_header("Register Number")]
            name_key = header_map[self._normalise_header("Student Name")]
            register_value = (row_values.get(register_key) or "").strip()
            name_value = (row_values.get(name_key) or "").strip()
            register_no = register_value.upper()

            matches = self.student_repo.get_all_by_register_no(
                register_no,
                batch_id=section.batch_id,
                lock=lock_existing,
            )
            matching_names = [
                student for student in matches
                if self._normalise_student_name(student.name)
                == self._normalise_student_name(name_value)
            ]

            if not matches:
                existing = None
            elif len(matching_names) == 1:
                existing = matching_names[0]
            else:
                existing = None
                placement_conflicts += 1
                candidate_students = matching_names or matches
                candidate_ids = [student.id for student in candidate_students]
                identity_resolutions.append({
                    "row_number": row_index,
                    "register_no": register_no,
                    "uploaded_name": name_value,
                    "selected_student_id": None,
                    "selected_student_name": None,
                    "candidate_student_ids": candidate_ids,
                    "other_student_ids": [student.id for student in matches],
                    "resolution_status": "unresolved",
                    "destination_section_id": section.id,
                    "destination_section_name": section.name,
                })
                if not matching_names:
                    errors.append(
                        f"Row {row_index}: Register number '{register_no}' exists in this "
                        "Batch, but no existing student name matches the uploaded name. "
                        "No identity was selected or changed."
                    )
                else:
                    errors.append(
                        f"Row {row_index}: Register number '{register_no}' and name "
                        "match multiple existing student identities. Resolve the identity "
                        "before importing; no identity was selected or changed."
                    )
                classified_students.append({
                    "register_no": register_no,
                    "name": name_value,
                    "status": "conflict",
                    "existing_student_id": None,
                })
                continue

            if existing is None:
                classified_students.append({
                    "register_no": register_no,
                    "name": name_value,
                    "status": "new",
                    "existing_student_id": None,
                })
                new_students += 1
                continue

            placement_status, placement_message = self._classify_import_student(
                existing,
                section,
                lock=lock_existing,
            )
            if matches:
                identity_resolutions.append({
                    "row_number": row_index,
                    "register_no": register_no,
                    "uploaded_name": name_value,
                    "selected_student_id": existing.id,
                    "selected_student_name": existing.name,
                    "candidate_student_ids": [student.id for student in matching_names],
                    "other_student_ids": [
                        student.id for student in matches if student.id != existing.id
                    ],
                    "resolution_status": placement_status,
                    "destination_section_id": section.id,
                    "destination_section_name": section.name,
                })
            classified_students.append({
                "register_no": register_no,
                "name": name_value,
                "status": placement_status,
                "existing_student_id": existing.id,
            })
            if placement_status == "already_assigned":
                already_assigned += 1
            elif placement_status == "restorable":
                eligible_for_restoration += 1
                if placement_message and placement_message not in errors:
                    errors.append(placement_message)
            else:
                placement_conflicts += 1
                errors.append(f"Row {row_index}: {placement_message}")

        invalid_count = len(invalid_rows)

        preview = {
            "section_id": section_id,
            "batch_id": section.batch_id,
            "total_rows": rows_total,
            "valid_rows": new_students + already_assigned + eligible_for_restoration,
            "invalid_rows": invalid_count,
            "new_students": new_students,
            "already_assigned": already_assigned,
            "eligible_for_restoration": eligible_for_restoration,
            "placement_conflicts": placement_conflicts,
            "duplicate_register_numbers": sorted(duplicate_register_numbers),
            "identity_resolutions": identity_resolutions,
            "errors": errors,
        }
        return preview, classified_students

    def _classify_import_student(
        self,
        student: Student,
        section: Any,
        lock: bool = False,
    ) -> Tuple[str, Optional[str]]:
        if student.archived_at is not None:
            return "conflict", (
                f"Register number '{student.register_no}' belongs to archived student "
                f"(student ID {student.id}); restore the archived identity separately."
            )

        current = self.student_repo.get_current_placement(student.id, lock=lock)
        if current is not None and current.section_id == section.id:
            return "already_assigned", None
        if current is not None and current.section_id is not None:
            return "conflict", (
                f"Register number '{student.register_no}' is actively assigned to another "
                f"Section (student ID {student.id}); it was not moved."
            )

        previous = current or self.student_repo.get_latest_placement(student.id)
        if previous is None:
            return "conflict", (
                f"Register number '{student.register_no}' has no placement history to verify "
                f"against this academic context (student ID {student.id})."
            )

        if (
            previous.batch_id != section.batch_id
            or previous.department_id != section.department_id
            or previous.year_id != section.year_id
        ):
            return "conflict", (
                f"Register number '{student.register_no}' has an incompatible prior academic "
                f"context (student ID {student.id}); it was not moved."
            )

        if previous.section_name and previous.section_name != section.name:
            return "conflict", (
                f"Register number '{student.register_no}' was previously assigned to logical "
                f"Section {previous.section_name}, not Section {section.name} "
                f"(student ID {student.id})."
            )

        legacy_context_note = None
        if previous.section_name is None:
            legacy_context_note = (
                f"Some students have matching Batch, Department, and Year placement history, "
                f"but the previous Section name was not recorded. Confirm Section {section.name} "
                "is the intended destination before restoration."
            )
        return "restorable", legacy_context_note

    def preview_student_import(
        self,
        section_id: int,
        uploaded_file: UploadFile,
        semester_id: Optional[int] = None,
    ) -> dict:
        rows, _ = self._parse_student_import_file(uploaded_file)
        preview, _ = self._validate_student_import_rows(section_id, rows, semester_id)
        return preview

    def import_student_batch(
        self,
        section_id: int,
        uploaded_file: UploadFile,
        semester_id: Optional[int] = None,
    ) -> dict:
        rows, _ = self._parse_student_import_file(uploaded_file)
        imported_count = 0
        restored_count = 0
        placed_count = 0
        already_assigned = 0
        skipped_conflict_count = 0
        try:
            with self.db.begin_nested():
                preview, classified_students = self._validate_student_import_rows(
                    section_id,
                    rows,
                    semester_id,
                    lock_existing=True,
                )
                if preview["total_rows"] == 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="The uploaded roster contains no student rows.",
                    )
                if preview["invalid_rows"] > 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Import contains invalid rows. Please review the validation errors before importing.",
                    )
                section = self.section_repo.get_by_id(section_id)
                if section is None or section.batch_id is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Selected section or its Batch was not found.",
                    )

                for student_data in classified_students:
                    if student_data["status"] == "conflict":
                        skipped_conflict_count += 1
                        continue

                    if student_data["status"] == "already_assigned":
                        already_assigned += 1
                        continue

                    if student_data["status"] == "new":
                        self.student_repo.create(
                            register_no=student_data["register_no"],
                            name=student_data["name"],
                            batch_id=section.batch_id,
                            section=section,
                            semester_id=semester_id,
                            commit=False,
                        )
                        imported_count += 1
                        placed_count += 1
                        continue

                    student = self.student_repo.get_by_id_for_update(
                        student_data["existing_student_id"]
                    )
                    if (
                        student is None
                        or student.batch_id != section.batch_id
                        or student.register_no.strip().upper() != student_data["register_no"]
                        or self._normalise_student_name(student.name)
                        != self._normalise_student_name(student_data["name"])
                    ):
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=(
                                f"Student identity for register number '{student_data['register_no']}' "
                                "changed or no longer matches the uploaded name during import. "
                                "Preview the roster again."
                            ),
                        )
                    self.student_repo.move_to_section(
                        student,
                        section,
                        semester_id=semester_id,
                        commit=False,
                    )
                    restored_count += 1
                    placed_count += 1
        except IntegrityError as error:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The roster changed while it was being imported. No student identities or placements were duplicated; preview the file again.",
            ) from error
        self.db.commit()

        return {
            "section_id": section_id,
            "batch_id": preview["batch_id"],
            "imported_count": imported_count,
            "restored_count": restored_count,
            "already_assigned_count": already_assigned,
            "placed_count": placed_count,
            "skipped_conflict_count": skipped_conflict_count,
            "message": (
                f"Created {imported_count} new student identities, restored {restored_count} "
                f"existing students to Section {section.name}, left {already_assigned} "
                f"already-assigned students unchanged, and skipped {skipped_conflict_count} "
                "placement conflicts. Conflicting students were not changed."
            ),
        }

    def list_students(
        self,
        department_id: Optional[int] = None,
        year_id: Optional[int] = None,
        section_id: Optional[int] = None,
        batch_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
        include_archived: bool = False,
    ) -> List[Student]:
        return self.student_repo.filter_students(
            department_id=department_id,
            year_id=year_id,
            section_id=section_id,
            batch_id=batch_id,
            skip=skip,
            limit=limit,
            include_archived=include_archived,
        )

    def get_students_by_section(self, section_id: int, include_archived: bool = False) -> List[Student]:
        section = self.section_repo.get_by_id(section_id)
        if not section:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
        return self.student_repo.get_by_section_id(section_id, include_archived=include_archived)

    def get_student_placements(self, student_id: int):
        self.get_student(student_id)
        return self.student_repo.get_placements(student_id)

    def create_student(self, payload: StudentCreate) -> Student:
        # Validate that the designated section exists
        section = self.section_repo.get_by_id(payload.section_id)
        if not section:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Designated section does not exist")
        if payload.batch_id is not None and payload.batch_id != section.batch_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Student Batch does not match the selected section.")
        if section.batch_id is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Selected section has no Batch context.")
        self._validate_section_semester(section, payload.semester_id)

        reg_no = payload.register_no.strip().upper()
        existing = self.student_repo.get_by_register_no(reg_no, batch_id=section.batch_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Register number '{reg_no}' already exists in this Batch. "
                    "Select the existing student to change their academic placement."
                ),
            )

        return self.student_repo.create(
            register_no=reg_no,
            name=payload.name.strip(),
            batch_id=section.batch_id,
            section=section,
            semester_id=payload.semester_id,
        )

    def move_student(self, student_id: int, payload: StudentPlacementUpdate) -> Student:
        student = self.get_student(student_id)
        section = self.section_repo.get_by_id(payload.section_id)
        if section is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Selected section does not exist.")
        if section.batch_id != student.batch_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Student cannot be moved to a different Batch.")
        self._validate_section_semester(section, payload.semester_id)
        current_section = student.section
        if (
            current_section is not None
            and current_section.year_id != section.year_id
            and current_section.batch_id == section.batch_id
            and current_section.department_id == section.department_id
            and current_section.name == section.name
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Changing the selected academic year within the same cohort Section "
                    "does not require changing the student's placement."
                ),
            )
        return self.student_repo.move_to_section(student, section, semester_id=payload.semester_id)

    def update_student(self, student_id: int, payload: StudentUpdate) -> Student:
        student = self.get_student(student_id)
        register_no = payload.register_no.strip().upper()
        name = payload.name.strip()

        if not register_no:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Register Number is required.")
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Student Name is required.")

        duplicate = self.student_repo.get_by_register_no(
            register_no,
            batch_id=student.batch_id,
            exclude_student_id=student.id,
        )
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Student with register number '{register_no}' already exists",
            )

        return self.student_repo.update(
            student=student,
            register_no=register_no,
            name=name,
        )

    def archive_student(self, student_id: int) -> Student:
        student = self.get_student(student_id)
        if student.archived_at is not None:
            return student
        return self.student_repo.set_archived(student, archived=True)

    def restore_student(self, student_id: int) -> Student:
        student = self.get_student(student_id)
        if student.archived_at is None:
            return student

        duplicate = self.student_repo.get_by_register_no(
            student.register_no,
            batch_id=student.batch_id,
            exclude_student_id=student.id,
        )
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot restore {student.register_no}: another active student in this section uses that register number.",
            )
        return self.student_repo.set_archived(student, archived=False)

    def _permanently_delete_archived_students(
        self,
        section_id: int,
        student_id: Optional[int] = None,
    ) -> int:
        if not self.section_repo.get_by_id(section_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")

        try:
            with self.db.begin_nested():
                deleted_count = self.student_repo.permanently_delete_archived_in_section(section_id, student_id)
            self.db.commit()
            return deleted_count
        except Exception:
            self.db.rollback()
            raise

    def permanently_delete_archived_students(self, section_id: int) -> int:
        return self._permanently_delete_archived_students(section_id)

    def permanently_delete_archived_student(self, student_id: int) -> int:
        student = self.get_student(student_id)
        if student.archived_at is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only archived students can be permanently deleted.",
            )
        if student.section_id is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Archived student has no current section placement.")
        return self._permanently_delete_archived_students(student.section_id, student_id)
