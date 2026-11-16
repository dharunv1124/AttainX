"""
SQLAlchemy ORM models for master data and authentication.
Sections and students follow Department -> Year -> Section -> Students.
Subjects remain independent of students.
"""

import enum
from sqlalchemy import (
    Boolean,
    Column,
    JSON,
    Integer,
    String,
    Date,
    DateTime,
    ForeignKey,
    Enum as SAEnum,
    UniqueConstraint,
    CheckConstraint,
    Index,
    Numeric,
    func,
    text,
)
from sqlalchemy.orm import relationship
from app.db.base import Base


class UserRole(str, enum.Enum):
    """Four confirmed roles in the OBE system."""
    ADMIN = "ADMIN"
    FACULTY = "FACULTY"
    CLASS_ADVISOR = "CLASS_ADVISOR"
    HOD = "HOD"


class User(Base):
    """User account entity with secure password hashing and role assignment."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    role = Column(
        SAEnum(UserRole, name="user_role_enum", native_enum=False),
        nullable=False,
        default=UserRole.FACULTY,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<User id={self.id} username='{self.username}' role='{self.role}'>"


class Batch(Base):
    """Academic admissions cohort. Example: 2024–28, 2025–29."""
    __tablename__ = "batches"

    id = Column(Integer, primary_key=True, index=True)
    batch_name = Column(String(50), unique=True, nullable=False)
    start_year = Column(Integer, nullable=False)
    end_year = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    sections = relationship("Section", back_populates="batch")
    students = relationship("Student", back_populates="batch")
    subjects = relationship("Subject", back_populates="batch")
    exams = relationship("Exam", back_populates="batch")

    __table_args__ = (
        UniqueConstraint("start_year", "end_year", name="uq_batch_year_range"),
    )

    def __repr__(self) -> str:
        return f"<Batch id={self.id} batch_name='{self.batch_name}'>"

    @property
    def is_default(self) -> bool:
        return self.start_year == 2024 and self.end_year == 2028


class Department(Base):
    """Academic Department entity (e.g. CSE, IT, ECE)."""
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    sections = relationship("Section", back_populates="department", cascade="all, delete-orphan")
    subjects = relationship("Subject", back_populates="department")

    def __repr__(self) -> str:
        return f"<Department id={self.id} code='{self.code}' name='{self.name}'>"


class Year(Base):
    """Academic year level: 1st Year, 2nd Year, 3rd Year, 4th Year."""
    __tablename__ = "years"

    id = Column(Integer, primary_key=True, index=True)
    year_number = Column(Integer, unique=True, nullable=False)
    name = Column(String(20), unique=True, nullable=False)  # "1st Year", "2nd Year", "3rd Year", "4th Year"

    # Relationships
    semesters = relationship("Semester", back_populates="year")
    sections = relationship("Section", back_populates="year")
    subjects = relationship("Subject", back_populates="year")

    def __repr__(self) -> str:
        return f"<Year id={self.id} year_number={self.year_number} name='{self.name}'>"


class Semester(Base):
    """Semester level: 1 through 8."""
    __tablename__ = "semesters"

    id = Column(Integer, primary_key=True, index=True)
    semester_number = Column(Integer, unique=True, nullable=False)
    name = Column(String(20), unique=True, nullable=False)  # "Semester 1" through "Semester 8"
    year_id = Column(Integer, ForeignKey("years.id", ondelete="RESTRICT"), nullable=False)

    # Relationships
    year = relationship("Year", back_populates="semesters")
    subjects = relationship("Subject", back_populates="semester")

    def __repr__(self) -> str:
        return f"<Semester id={self.id} semester_number={self.semester_number} name='{self.name}'>"


class Section(Base):
    """
    Section/Class entity representing a Department and Year cohort.
    Batch scope is required so the same Year + Section name can exist across batches.
    """
    __tablename__ = "sections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(20), nullable=False)  # "A", "B", "C"
    batch_id = Column(Integer, ForeignKey("batches.id", ondelete="RESTRICT"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    year_id = Column(Integer, ForeignKey("years.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    batch = relationship("Batch", back_populates="sections")
    department = relationship("Department", back_populates="sections")
    year = relationship("Year", back_populates="sections")
    students = relationship("Student", back_populates="section")

    __table_args__ = (
        UniqueConstraint("batch_id", "department_id", "year_id", "name", name="uq_batch_dept_year_section"),
        Index("idx_section_lookup", "batch_id", "department_id", "year_id"),
    )

    def __repr__(self) -> str:
        return f"<Section id={self.id} name='{self.name}' batch_id={self.batch_id} dept_id={self.department_id} year_id={self.year_id}>"


class Student(Base):
    """
    Student entity.
    Student identity is batch-scoped; section_id is the current placement
    compatibility pointer. StudentAcademicPlacement is the placement history.
    """
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    register_no = Column(String(50), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.id", ondelete="RESTRICT"), nullable=False, index=True)
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="RESTRICT"), nullable=True, index=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    batch = relationship("Batch", back_populates="students")
    section = relationship("Section", back_populates="students")
    academic_placements = relationship(
        "StudentAcademicPlacement",
        back_populates="student",
        cascade="all, delete-orphan",
        order_by="StudentAcademicPlacement.effective_from",
    )

    def __repr__(self) -> str:
        return f"<Student id={self.id} register_no='{self.register_no}' name='{self.name}'>"


class StudentAcademicPlacement(Base):
    """A dated academic placement for a stable batch-scoped student identity."""
    __tablename__ = "student_academic_placements"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id", ondelete="RESTRICT"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False)
    year_id = Column(Integer, ForeignKey("years.id", ondelete="RESTRICT"), nullable=False)
    semester_id = Column(Integer, ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=True)
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="RESTRICT"), nullable=True, index=True)
    section_name = Column(String(20), nullable=True)
    is_current = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    effective_from = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    effective_to = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    student = relationship("Student", back_populates="academic_placements")
    batch = relationship("Batch")
    department = relationship("Department")
    year = relationship("Year")
    semester = relationship("Semester")
    section = relationship("Section")

    __table_args__ = (
        Index(
            "uq_student_current_academic_placement",
            "student_id",
            unique=True,
            sqlite_where=text("is_current = 1"),
            postgresql_where=text("is_current"),
        ),
        Index("idx_placement_section_current", "section_id", "is_current"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_student_placement_effective_dates",
        ),
    )


class Subject(Base):
    """
    Subject master data entity scoped by Department, Year, Semester, and Batch.
    Null scope is reserved for unmappable pre-scope legacy records.
    """
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id", ondelete="RESTRICT"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="RESTRICT"), nullable=True)
    year_id = Column(Integer, ForeignKey("years.id", ondelete="RESTRICT"), nullable=True)
    semester_id = Column(Integer, ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    batch = relationship("Batch", back_populates="subjects")
    department = relationship("Department", back_populates="subjects")
    year = relationship("Year", back_populates="subjects")
    semester = relationship("Semester", back_populates="subjects")

    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "department_id",
            "year_id",
            "semester_id",
            "name",
            name="uq_subject_batch_department_year_semester_name",
        ),
        CheckConstraint(
            "(department_id IS NULL AND year_id IS NULL AND semester_id IS NULL) "
            "OR (department_id IS NOT NULL AND year_id IS NOT NULL AND semester_id IS NOT NULL)",
            name="ck_subject_scope_all_or_none",
        ),
    )

    def __repr__(self) -> str:
        return f"<Subject id={self.id} name='{self.name}' batch_id={self.batch_id} department_id={self.department_id} year_id={self.year_id} semester_id={self.semester_id}>"


class Exam(Base):
    """
    Exam configuration entity.
    Tied to the selected class (Batch -> Department -> Year -> Semester -> Section) and subject.
    Stores covered COs, pass percentage, and questions.
    """
    __tablename__ = "exams"

    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "department_id",
            "year_id",
            "semester_id",
            "section_id",
            "subject_id",
            "name",
            name="uq_exam_batch_class_subject_name",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    exam_type = Column(String(50), nullable=False, default="CUSTOM")  # INTERNAL_1, INTERNAL_2, MODEL, CUSTOM
    batch_id = Column(Integer, ForeignKey("batches.id", ondelete="RESTRICT"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False)
    year_id = Column(Integer, ForeignKey("years.id", ondelete="RESTRICT"), nullable=False)
    semester_id = Column(Integer, ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False)
    pass_percentage = Column(Numeric(5, 2), nullable=False)
    exam_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    batch = relationship("Batch", back_populates="exams")
    department = relationship("Department")
    year = relationship("Year")
    semester = relationship("Semester")
    section = relationship("Section")
    subject = relationship("Subject")
    covered_cos = relationship("ExamCoveredCO", back_populates="exam", cascade="all, delete-orphan", order_by="ExamCoveredCO.co_code")
    questions = relationship("ExamQuestion", back_populates="exam", cascade="all, delete-orphan", order_by="ExamQuestion.id")

    def __repr__(self) -> str:
        return f"<Exam id={self.id} name='{self.name}' type='{self.exam_type}' batch_id={self.batch_id}>"


class ExamCoveredCO(Base):
    """
    Covered Course Outcome (CO) selected by faculty for an exam.
    Faculty explicitly selects covered COs (never inferred).
    """
    __tablename__ = "exam_covered_cos"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True)
    co_code = Column(String(20), nullable=False)  # e.g., "CO1", "CO2"

    exam = relationship("Exam", back_populates="covered_cos")

    __table_args__ = (
        UniqueConstraint("exam_id", "co_code", name="uq_exam_covered_co"),
    )

    def __repr__(self) -> str:
        return f"<ExamCoveredCO exam_id={self.exam_id} co='{self.co_code}'>"


class ExamQuestion(Base):
    """
    Question configuration for an exam.
    Belongs to a specific exam.
    Each question has Question Number, Maximum Marks, and exactly one mapped CO.
    The mapped CO must be in the exam's covered COs list.
    """
    __tablename__ = "exam_questions"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True)
    question_number = Column(String(20), nullable=False)  # e.g. "Q1", "1"
    max_marks = Column(Numeric(5, 2), nullable=False)  # e.g. 2.00, 10.00
    co_code = Column(String(20), nullable=False)  # e.g. "CO1"

    exam = relationship("Exam", back_populates="questions")

    __table_args__ = (
        UniqueConstraint("exam_id", "question_number", name="uq_exam_question_number"),
    )

    def __repr__(self) -> str:
        return f"<ExamQuestion exam_id={self.exam_id} q='{self.question_number}' max={self.max_marks} co='{self.co_code}'>"


class StudentMark(Base):
    """
    Student obtained mark for a specific question in an exam.
    Persisted for Phase 6 marks-entry workspace.
    """
    __tablename__ = "student_marks"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    question_number = Column(String(20), nullable=False)
    obtained_mark = Column(Numeric(5, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    exam = relationship("Exam")
    student = relationship("Student")

    __table_args__ = (
        UniqueConstraint("exam_id", "student_id", "question_number", name="uq_exam_student_question_mark"),
        Index("idx_student_mark_lookup", "exam_id", "student_id"),
    )

    def __repr__(self) -> str:
        return f"<StudentMark exam_id={self.exam_id} student_id={self.student_id} q='{self.question_number}' mark={self.obtained_mark}>"


class CourseCOPOMapping(Base):
    """Manual CO–PO matrix scoped to a subject and section."""
    __tablename__ = "course_co_po_mappings"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="CASCADE"), nullable=True)
    mapping_data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    subject = relationship("Subject")

    __table_args__ = (
        UniqueConstraint("subject_id", "section_id", name="uq_course_co_po_mapping_subject_section"),
    )


class CourseCOAttainmentInputs(Base):
    """Staff-entered Table 2 inputs scoped to a subject and section."""
    __tablename__ = "course_co_attainment_inputs"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="CASCADE"), nullable=True)
    input_data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    subject = relationship("Subject")

    __table_args__ = (
        UniqueConstraint("subject_id", "section_id", name="uq_course_co_attainment_subject_section"),
    )


class SavedCustomExamPattern(Base):
    """Reusable grouped custom exam pattern; independent of created exams."""
    __tablename__ = "saved_custom_exam_patterns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    groups = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
