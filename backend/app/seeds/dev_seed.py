"""
Database seed script for foundational master data and users.
Seeds:
- 4 Academic Years: 1st Year to 4th Year
- 8 Semesters: Semester 1 to Semester 8 mapped to Years
- Users for all 4 confirmed roles (Admin, Faculty, Class Advisor, HOD)
- Sample Department (CSE)
- Sample Sections A/B/C in 3rd Year
- CSE 3rd Year Subjects by Semester
"""

import os

from sqlalchemy.orm import Session
from app.db.session import SessionLocal, engine
from app.db.base import Base
from app.db.models import (
    Batch, User, UserRole, Department, Year, Semester, Section, Student,
    StudentAcademicPlacement, Subject,
)
from app.security.auth import hash_password


def seed_database(db: Session) -> None:
    print("Beginning database seeding...")

    # 1. Seed academic batches; preserve legacy records under the default 2024–28 cohort.
    default_batch = db.query(Batch).filter(Batch.batch_name == "2024–28").first()
    if not default_batch:
        default_batch = Batch(batch_name="2024–28", start_year=2024, end_year=2028)
        db.add(default_batch)
        db.flush()
    current_batch_id = default_batch.id

    # 2. Seed Years (1st Year, 2nd Year, 3rd Year, 4th Year)
    years_data = [
        (1, "1st Year"),
        (2, "2nd Year"),
        (3, "3rd Year"),
        (4, "4th Year"),
    ]
    year_map = {}
    for num, name in years_data:
        yr = db.query(Year).filter(Year.year_number == num).first()
        if not yr:
            yr = Year(year_number=num, name=name)
            db.add(yr)
            db.flush()
            print(f"Created Year: {name}")
        year_map[num] = yr

    # 3. Seed Semesters (1 through 8)
    semesters_data = [
        (1, "Semester 1", 1),
        (2, "Semester 2", 1),
        (3, "Semester 3", 2),
        (4, "Semester 4", 2),
        (5, "Semester 5", 3),
        (6, "Semester 6", 3),
        (7, "Semester 7", 4),
        (8, "Semester 8", 4),
    ]
    sem_map = {}
    for sem_num, sem_name, yr_num in semesters_data:
        sem = db.query(Semester).filter(Semester.semester_number == sem_num).first()
        if not sem:
            sem = Semester(
                semester_number=sem_num,
                name=sem_name,
                year_id=year_map[yr_num].id,
            )
            db.add(sem)
            db.flush()
            print(f"Created Semester: {sem_name}")
        sem_map[sem_num] = sem

    # 4. Seed Users for all 4 confirmed roles
    users_data = [
        ("admin", "admin@obe.edu", "Admin User", UserRole.ADMIN, "OBE_SEED_ADMIN_PASSWORD"),
        ("faculty1", "faculty@obe.edu", "Faculty User", UserRole.FACULTY, "OBE_SEED_FACULTY_PASSWORD"),
        ("advisor1", "advisor@obe.edu", "Class Advisor", UserRole.CLASS_ADVISOR, "OBE_SEED_ADVISOR_PASSWORD"),
        ("hod_cse", "hod@obe.edu", "Department Head", UserRole.HOD, "OBE_SEED_HOD_PASSWORD"),
    ]
    for username, email, full_name, role, password_env in users_data:
        u = db.query(User).filter(User.username == username).first()
        if not u:
            password = os.getenv(password_env)
            if not password:
                raise RuntimeError(f"{password_env} must be set before creating the {role.value} user.")
            u = User(
                username=username,
                email=email,
                full_name=full_name,
                role=role,
                hashed_password=hash_password(password),
            )
            db.add(u)
            print(f"Created User: {username} ({role.value})")

    # 5. Seed required departments without duplicating existing master records.
    departments_data = [
        ("Computer Science and Engineering", "CSE"),
        ("Information Technology", "IT"),
        ("Electronics and Communication Engineering", "ECE"),
        ("Artificial Intelligence and Machine Learning", "AIML"),
        ("Internet of Things", "IOT"),
        ("Electrical and Electronics Engineering", "EEE"),
        ("Robotics and Automation", "RA"),
        ("Mechanical Engineering", "MECH"),
        ("Food Technology", "FT"),
    ]
    departments_by_code = {
        department.code.strip().upper(): department
        for department in db.query(Department).all()
    }
    departments_by_name = {
        department.name.strip().casefold(): department
        for department in departments_by_code.values()
    }
    for name, code in departments_data:
        department = departments_by_code.get(code) or departments_by_name.get(name.casefold())
        if department:
            if department.code.strip().upper() != code and code not in departments_by_code:
                department.code = code
                departments_by_code[code] = department
            continue

        department = Department(name=name, code=code)
        db.add(department)
        db.flush()
        departments_by_code[code] = department
        departments_by_name[name.casefold()] = department
        print(f"Created Department: {code}")

    dept_cse = departments_by_code["CSE"]

    # 6. Seed one Section A/B/C cohort per CSE year, independently of semester.
    cse_sections = {}
    for year_number, year in year_map.items():
        for section_name in ("A", "B", "C"):
            section = db.query(Section).filter(
                Section.batch_id == current_batch_id,
                Section.department_id == dept_cse.id,
                Section.year_id == year.id,
                Section.name == section_name,
            ).first()
            if not section:
                section = Section(
                    name=section_name,
                    batch_id=current_batch_id,
                    department_id=dept_cse.id,
                    year_id=year.id,
                )
                db.add(section)
                db.flush()
                print(f"Created Section: CSE {year.name} - Section {section_name}")
            cse_sections[(year_number, section_name)] = section
    sec_a = cse_sections[(3, "A")]

    # 7. Seed synthetic students only; real rosters must be imported by an administrator.
    students_sample = [
        ("TEST-REG-0001", "Sample Student 1"),
        ("TEST-REG-0002", "Sample Student 2"),
        ("TEST-REG-0003", "Sample Student 3"),
        ("TEST-REG-0004", "Sample Student 4"),
        ("TEST-REG-0005", "Sample Student 5"),
    ]
    for reg_no, student_name in students_sample:
        student = db.query(Student).filter(
            Student.batch_id == current_batch_id,
            Student.register_no == reg_no,
        ).first()
        if not student:
            student = Student(
                register_no=reg_no,
                name=student_name,
                batch_id=current_batch_id,
                section_id=sec_a.id,
            )
            db.add(student)
            db.flush()
        if not db.query(StudentAcademicPlacement).filter(
            StudentAcademicPlacement.student_id == student.id,
            StudentAcademicPlacement.is_current.is_(True),
        ).first():
            db.add(StudentAcademicPlacement(
                student_id=student.id,
                batch_id=current_batch_id,
                department_id=sec_a.department_id,
                year_id=sec_a.year_id,
                semester_id=sem_map[5].id,
                section_id=sec_a.id,
                is_current=True,
                effective_from=student.created_at,
            ))

    # 8. Seed confirmed CSE 3rd Year Subjects by Semester, never by Section.
    curriculum = {
        5: (
            "DATABASE SYSTEM",
            "COMPUTER NETWORKS",
            "OPERATING SYSTEM",
            "THEORY OF COMPUTATION",
            "SOFTWARE ENGINEERING",
        ),
        6: (
            "WEB TECHNOLOGIES",
            "COMPILER DESIGN",
            "DISTRIBUTED COMPUTING SYSTEM",
            "ARTIFICIAL INTELLIGENCE AND MACHINE LEARNING",
        ),
    }

    incorrect_semester_6_subjects = (
        "DATABASE MANAGEMENT SYSTEMS",
        "THEORY OF COMPUTATION",
    )
    for subject in db.query(Subject).filter(
        Subject.department_id == dept_cse.id,
        Subject.year_id == year_map[3].id,
        Subject.semester_id == sem_map[6].id,
        Subject.name.in_(incorrect_semester_6_subjects),
    ):
        subject.department_id = None
        subject.year_id = None
        subject.semester_id = None

    for semester_number, subject_names in curriculum.items():
        for subject_name in subject_names:
            subject = db.query(Subject).filter(
                Subject.department_id == dept_cse.id,
                Subject.year_id == year_map[3].id,
                Subject.semester_id == sem_map[semester_number].id,
                Subject.name == subject_name,
            ).first()
            if not subject:
                db.add(Subject(
                    name=subject_name,
                    batch_id=current_batch_id,
                    department_id=dept_cse.id,
                    year_id=year_map[3].id,
                    semester_id=sem_map[semester_number].id,
                ))
                print(f"Created CSE 3rd Year Semester {semester_number} Subject: {subject_name}")
            elif subject.batch_id is None:
                subject.batch_id = current_batch_id

    for section in db.query(Section).filter(Section.batch_id.is_(None)):
        section.batch_id = current_batch_id
    for subject in db.query(Subject).filter(Subject.batch_id.is_(None)):
        subject.batch_id = current_batch_id

    db.commit()
    print("Database seeding completed successfully.")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
