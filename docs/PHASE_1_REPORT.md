# Phase 1 Discovery and Verification Report

## 1. Domain Discovery
- Departmental workflow relies on question-wise mark entry rather than aggregate CO scores.
- Calculations must roll up from raw question entries to student CO performance.
- Master data entities: Department, Year, Semester, Section, Student, Subject.

## 2. Integrity and Relationship Directives
- Students belong to a Class/Section, never to a Subject.
- A Subject is independent of Students.
- Authentication supports 4 confirmed roles: Admin, Faculty, Class Advisor, HOD.
- Password hashes must be stored using industry-standard hashing (Bcrypt).
