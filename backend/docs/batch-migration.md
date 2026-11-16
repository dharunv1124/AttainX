# Batch identity and migration notes

## Data model

- `batches` represents an admissions cohort; the `2024–28` batch is inserted as the existing-data cohort.
- Student identity is stable across a Batch. Imports classify an existing Batch/register-number identity by its placement and reuse it only for an eligible restoration; historic duplicate identities are reported as conflicts and remain intact for review. There is intentionally no database uniqueness constraint because historic conflicting rows must not be deleted or merged automatically.
- `student_academic_placements` records placement changes and snapshots `section_name` so the logical Section identity survives deletion and recreation. `students.section_id` remains a compatibility pointer to the current section and is updated together with the active placement.
- Marks continue to reference the original `student_id` and `exam_id`; a placement change does not rewrite marks, exams, Course OBE data, or student identity.
- Legacy student rows only identify their Section and Year, not their Semester. Their initial placement therefore keeps `semester_id` NULL rather than claiming an unknown semester. Future placements record the selected Semester.
- A legacy subject without a Department/Year/Semester is assigned a specific scope only when all of its existing Exams agree on the same Department, Year, and Semester. Ambiguous or unused legacy subjects remain unscoped and preserved in the `2024–28` Batch; they are not shown in context-specific Subject selectors until staff resolve their scope.

## Migration safety

Revision `016_batch_student_placement` follows `015_course_obe_section_scope`. It explicitly adds the Batch and placement schema, assigns every existing Section, Subject, Student and Exam to `2024–28`, and inserts one initial placement per existing Student. It does not copy or recreate students, exams, subjects, sections, marks, or Course OBE rows.

The SQLite migration requires an existing, separate backup path in `OBE_DB_BACKUP_PATH`. Under a SQLite write lock, before DDL it checks that the backup passes `PRAGMA integrity_check`, has the same Alembic revision as the source, and has exactly matching table names and row contents. SQLite foreign-key enforcement is temporarily disabled only around this migration's table rebuilds; the migration checks foreign-key integrity before commit and Alembic checks it again after restoring enforcement.

Create a verified backup with the SQLite backup API helper before any approved operational migration. For example, from the repository root:

```powershell
.\.venv\Scripts\python.exe backend\scripts\backup_database.py `
  backend\obe_db.sqlite backend\obe_db_pre_batch.sqlite
$env:OBE_DB_BACKUP_PATH = (Resolve-Path backend\obe_db_pre_batch.sqlite).Path
```

Do not run the migration against an operational database without explicit approval and a verified backup. Tests use isolated temporary databases.

The migration preserves existing duplicate register numbers and drops the legacy section-level unique index so future duplicate validation is handled consistently by the application. It stops before schema changes for dangling student/exam references, inconsistent exam/section contexts, duplicate records that would violate the new scoped keys, or a missing/mismatched backup. It does not merge, rename, archive, or delete student records.

Historical duplicate register numbers may be retained as data-quality conflicts; do not merge, rename, archive, or delete them automatically.

Revision `018_student_placement_logical_section` adds the nullable placement snapshot `section_name` and backfills it wherever a placement still references a Section. It intentionally does not infer a logical Section for already-detached legacy placements because their prior Section ID and name may no longer be recoverable. Such rows can be previewed for restoration only when Batch, Department, and Year match the selected destination; the import preview clearly warns that the previous Section name is unknown and requires the user to verify the destination. New section deletions always preserve the exact Section name before clearing the Section foreign key.

Revision 018 must be applied through the existing Alembic process after reviewing the target database and taking the required approved backup. For a database already at revision 017, set `DATABASE_URL` to the explicitly approved target and run from `backend`:

```powershell
$env:DATABASE_URL = "<approved database URL>"
..\.venv\Scripts\python.exe -m alembic upgrade 018_student_placement_logical_section
```

It is not run automatically by application startup. Do not apply it to `backend/obe_db.sqlite` as part of this task. If the target is earlier than revision 017, review and follow the backup and preflight requirements of every intervening migration first. Downgrading revision 018 discards the Section-name snapshots and is unsafe after a Section has been deleted.

## Remaining legacy-data follow-up

An unscoped legacy Subject is assigned an academic scope only when all associated Exams agree on one Department, Year, and Semester. The audited operational database has two such subjects; each is mapped to CSE, 3rd Year, Semester 6. Unused or ambiguous unscoped subjects remain preserved but are not included in context-specific selectors until staff resolve their scope.
