# OBE System Requirements & Architecture Specification

## 1. System Objective
Outcome-Based Education (OBE) Course Outcome (CO) calculation and attainment platform.

## 2. Core Entities & Hierarchy
- **Department**: Academic departments (e.g. CSE, IT, ECE).
- **Year**: Academic progress levels: "1st Year", "2nd Year", "3rd Year", "4th Year" (explicitly distinct from batch/calendar years).
- **Semester**: Semesters 1 through 8.
- **Section**: Classes within a department/year/semester (e.g. "A", "B", "C").
- **Student**: Belongs to a section (Department -> Year -> Semester -> Section -> Student). Register Number, Student Name.
- **Subject**: Independent master data. Contains Subject Name only.
- **User Roles**: ADMIN, FACULTY, CLASS_ADVISOR, HOD.

## 3. Pure Calculation Engine (Phase 3 Confirmed)
- **CO Maximum Marks**: Sum of question maximum marks mapped to the CO.
- **CO Obtained Marks**: Sum of student marks obtained on questions mapped to the CO.
- **CO Percentage**: (Obtained / Maximum) * 100.
- **Attainment**: Strict `>` comparison: `1` if CO Percentage > Pass Percentage, else `0`.
- Rounding/precision: Implementation choice pending final departmental confirmation.

## 4. Discrepancies & Unresolved Items
- **Model Exam Structure Discrepancy**: Confirmed requirement is 15 questions (10 x 2m + 5 x 8m = 60m), while the historical workbook sheet has 20 columns (Q1-Q20). Engine is completely dynamic.
- **Absence / Incomplete Marks**: Incomplete marks raise `IncompleteDataError` without guessing an unconfirmed policy.
- **Role Permissions**: Detailed authorization matrix is UNRESOLVED pending departmental policy.
