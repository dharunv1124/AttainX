import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { Student, StudentImportPreview } from '../types';
import { addStudent, deleteStudent, importStudentList, loadSectionStudents, permanentlyDeleteArchivedStudent, permanentlyDeleteArchivedStudents, previewStudentImport, restoreStudent, updateStudent } from '../services/studentService';

interface StudentManagementProps {
  sectionId: number;
  semesterId: number;
  sectionName?: string;
  batchName?: string;
  departmentName?: string;
  yearName?: string;
  students: Student[];
  loading: boolean;
  onStudentAdded: () => Promise<void>;
}

const StudentManagementContent: React.FC<StudentManagementProps> = ({
  sectionId,
  semesterId,
  sectionName,
  batchName,
  departmentName,
  yearName,
  students,
  loading,
  onStudentAdded,
}) => {
  const [registerNo, setRegisterNo] = useState('');
  const [name, setName] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [editingStudentId, setEditingStudentId] = useState<number | null>(null);
  const [editRegisterNo, setEditRegisterNo] = useState('');
  const [editName, setEditName] = useState('');
  const [deletingStudentId, setDeletingStudentId] = useState<number | null>(null);
  const [archivingAll, setArchivingAll] = useState(false);
  const [restoringStudentId, setRestoringStudentId] = useState<number | null>(null);
  const [permanentlyDeletingArchived, setPermanentlyDeletingArchived] = useState(false);
  const [permanentlyDeletingStudentId, setPermanentlyDeletingStudentId] = useState<number | null>(null);
  const [showArchivedStudents, setShowArchivedStudents] = useState(false);
  const [archivedStudents, setArchivedStudents] = useState<Student[]>([]);
  const [archivedLoading, setArchivedLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<StudentImportPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [rosterExpanded, setRosterExpanded] = useState(false);
  const importInputRef = useRef<HTMLInputElement>(null);
  const previewRequestInFlight = useRef(false);
  const importRequestInFlight = useRef(false);
  const identityResolutions = preview?.identity_resolutions ?? [];
  const duplicateRegisterNumbers = preview?.duplicate_register_numbers ?? [];
  const previewNotes = preview?.errors ?? [];

  useEffect(() => {
    setRosterExpanded(false);
    setShowArchivedStudents(false);
    setArchivedStudents([]);
  }, [sectionId]);

  useEffect(() => {
    setPreview(null);
  }, [sectionId, semesterId]);

  const refreshArchivedStudents = async () => {
    setArchivedLoading(true);
    try {
      const roster = await loadSectionStudents(sectionId, true);
      setArchivedStudents(roster.filter((student) => student.archivedAt));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to load archived students.');
    } finally {
      setArchivedLoading(false);
    }
  };

  const toggleArchivedStudents = async () => {
    const shouldShow = !showArchivedStudents;
    setShowArchivedStudents(shouldShow);
    if (shouldShow) await refreshArchivedStudents();
  };

  const clearImportSelection = () => {
    setImportFile(null);
    setPreview(null);
    setMessage(null);
    if (importInputRef.current) {
      importInputRef.current.value = '';
    }
  };

  const handlePreviewImport = async () => {
    if (previewRequestInFlight.current) return;
    if (!importFile || !sectionId) {
      setMessage('Choose a CSV or XLSX file to preview the student roster import.');
      return;
    }

    previewRequestInFlight.current = true;
    setPreviewing(true);
    setMessage(null);
    try {
      const result = await previewStudentImport(sectionId, importFile, semesterId);
      setPreview(result);
      if (result.placement_conflicts > 0) {
        setMessage(`Preview found ${result.placement_conflicts} placement conflicts. No students will be moved.`);
      } else if (result.invalid_rows > 0) {
        setMessage(`Import preview found ${result.invalid_rows} invalid rows. Review the validation messages below.`);
      } else {
        setMessage(
          `Preview: ${result.new_students} new, ${result.already_assigned} already assigned, ` +
          `${result.eligible_for_restoration} eligible for restoration.`,
        );
      }
    } catch (error) {
      setPreview(null);
      setMessage(error instanceof Error ? error.message : 'Unable to preview the student roster import.');
    } finally {
      previewRequestInFlight.current = false;
      setPreviewing(false);
    }
  };

  const handleConfirmImport = async () => {
    if (importRequestInFlight.current) return;
    if (!importFile || !sectionId) {
      setMessage('Select a file and a section before importing the roster.');
      return;
    }
    if (!preview || preview.section_id !== sectionId) {
      setMessage('Preview the selected roster for this section before importing.');
      return;
    }

    const destination = [
      `Batch: ${batchName || 'Unknown'}`,
      `Department: ${departmentName || 'Unknown'}`,
      `Year: ${yearName || 'Unknown'}`,
      `Section: ${sectionName || 'Unknown'}`,
      '',
      `New students to create: ${preview.new_students}`,
      `Existing students to restore: ${preview.eligible_for_restoration}`,
      `Already assigned (unchanged): ${preview.already_assigned}`,
      `Placement conflicts to skip: ${preview.placement_conflicts}`,
      `Invalid rows: ${preview.invalid_rows}`,
      '',
      'Conflicting students will not be added, moved, or changed.',
    ].join('\n');
    if (!window.confirm(`Confirm roster destination:\n\n${destination}\n\nContinue?`)) return;

    importRequestInFlight.current = true;
    setImporting(true);
    setMessage(null);
    try {
      const result = await importStudentList(sectionId, importFile, semesterId);
      clearImportSelection();
      try {
        await onStudentAdded();
        setMessage(result.message || `Imported ${result.imported_count} new students and restored ${result.restored_count} existing students.`);
      } catch {
        setMessage(`${result.message} The roster could not be refreshed; reload it to see the updated students.`);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to import the student roster.');
    } finally {
      importRequestInFlight.current = false;
      setImporting(false);
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      await addStudent(registerNo, name, sectionId, semesterId);
      setRegisterNo('');
      setName('');
      await onStudentAdded();
      setMessage('Student added to the selected section.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to add student.');
    } finally {
      setSaving(false);
    }
  };

  const startEditing = (student: Student) => {
    setEditingStudentId(student.id);
    setEditRegisterNo(student.registerNo);
    setEditName(student.name);
    setMessage(null);
  };

  const cancelEditing = () => {
    setEditingStudentId(null);
    setEditRegisterNo('');
    setEditName('');
  };

  const handleSaveEdit = async (studentId: number) => {
    const trimmedRegisterNo = editRegisterNo.trim();
    const trimmedName = editName.trim();
    if (!trimmedRegisterNo || !trimmedName) {
      setMessage('Register Number and Student Name are required.');
      return;
    }

    setSaving(true);
    setMessage(null);
    try {
      await updateStudent(studentId, trimmedRegisterNo, trimmedName);
      cancelEditing();
      await onStudentAdded();
      setMessage('Student updated successfully.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to update student.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (student: Student) => {
    if (!window.confirm(`Archive ${student.name} (${student.registerNo}) from this section?`)) return;

    setDeletingStudentId(student.id);
    setMessage(null);
    try {
      await deleteStudent(student.id);
      await onStudentAdded();
      if (showArchivedStudents) await refreshArchivedStudents();
      setMessage('Student archived from the active roster.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to delete student.');
    } finally {
      setDeletingStudentId(null);
    }
  };

  const handleArchiveAll = async () => {
    const studentsToArchive = [...students];
    if (studentsToArchive.length === 0) return;
    if (!window.confirm(`Archive all ${studentsToArchive.length} active students from this section? They can be restored from Archived Students.`)) return;

    setArchivingAll(true);
    setMessage(null);
    let archivedCount = 0;
    let firstError: unknown = null;
    try {
      for (const student of studentsToArchive) {
        try {
          await deleteStudent(student.id);
          archivedCount += 1;
        } catch (error) {
          firstError ??= error;
        }
      }

      await onStudentAdded();
      if (showArchivedStudents) await refreshArchivedStudents();
      if (firstError) {
        const detail = firstError instanceof Error ? firstError.message : 'Unable to archive some students.';
        setMessage(`Archived ${archivedCount} of ${studentsToArchive.length} students. ${detail}`);
      } else {
        setMessage(`Archived all ${archivedCount} active students. They can be restored from Archived Students.`);
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : 'Unable to refresh the student list.';
      setMessage(`Archived ${archivedCount} of ${studentsToArchive.length} students. ${detail}`);
    } finally {
      setArchivingAll(false);
    }
  };

  const handleRestore = async (student: Student) => {
    setRestoringStudentId(student.id);
    setMessage(null);
    try {
      await restoreStudent(student.id);
      await onStudentAdded();
      setArchivedStudents((current) => current.filter((item) => item.id !== student.id));
      setMessage('Student restored to the active roster.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to restore student.');
    } finally {
      setRestoringStudentId(null);
    }
  };

  const handlePermanentlyDeleteArchived = async () => {
    const archivedCount = archivedStudents.length;
    if (archivedCount === 0) return;
    if (!window.confirm(`Are you sure you want to permanently delete all ${archivedCount} archived students and their OBE marks? This cannot be undone.`)) return;

    setPermanentlyDeletingArchived(true);
    setMessage(null);
    try {
      const deletedCount = await permanentlyDeleteArchivedStudents(sectionId);
      setArchivedStudents([]);
      setMessage(`Permanently deleted ${deletedCount} archived students and their OBE marks.`);
      try {
        await onStudentAdded();
      } catch {
        setMessage(`Permanently deleted ${deletedCount} archived students and their OBE marks. The active list could not be refreshed.`);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to permanently delete archived students.');
    } finally {
      setPermanentlyDeletingArchived(false);
    }
  };

  const handlePermanentlyDeleteArchivedStudent = async (student: Student) => {
    if (!window.confirm('Are you sure you want to permanently delete this student and their OBE marks? This cannot be undone.')) return;

    setPermanentlyDeletingStudentId(student.id);
    setMessage(null);
    try {
      await permanentlyDeleteArchivedStudent(student.id);
      setArchivedStudents((current) => current.filter((item) => item.id !== student.id));
      setMessage(`${student.name} and their OBE marks were permanently deleted.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to permanently delete archived student.');
    } finally {
      setPermanentlyDeletingStudentId(null);
    }
  };

  return (
    <section className="bg-white rounded-lg border border-slate-200 p-4 shadow-2xs">
      <button
        type="button"
        onClick={() => setRosterExpanded((expanded) => !expanded)}
        aria-expanded={rosterExpanded}
        className="flex w-full items-center justify-between border-b border-slate-100 pb-2 text-left"
      >
        <div>
          <h2 className="text-sm font-semibold text-slate-800 uppercase tracking-wider">Student Name List</h2>
          <p className="text-xs text-slate-500 mt-0.5">{sectionName ? `Section ${sectionName}` : 'Students in this section'}</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold text-blue-700">{students.length} students</span>
          <ChevronDown aria-hidden="true" className={`h-4 w-4 text-slate-500 transition-transform ${rosterExpanded ? 'rotate-180' : ''}`} />
        </div>
      </button>

      {rosterExpanded && (
        <>
          <div className="mt-3 flex items-center justify-between">
            <span className="text-xs text-slate-500">Active students: {students.length}</span>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={handleArchiveAll}
                disabled={loading || archivingAll || students.length === 0}
                className="text-xs font-semibold text-red-700 hover:text-red-900 disabled:opacity-50"
              >
                {archivingAll ? 'Removing...' : 'Remove All'}
              </button>
              <button type="button" onClick={toggleArchivedStudents} aria-expanded={showArchivedStudents} className="text-xs font-semibold text-slate-700 hover:text-slate-900">
                {showArchivedStudents ? 'Hide Archived Students' : 'Archived Students'}
              </button>
            </div>
          </div>
      <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-700">Import Student List</p>
            <p className="text-[11px] text-slate-500 mt-1">Accepted files: .csv or .xlsx. Required columns: Register Number, Student Name.</p>
          </div>
          <label className="inline-flex cursor-pointer items-center justify-center rounded-md border border-blue-600 bg-blue-600 px-3 py-2 text-[11px] font-semibold text-white hover:bg-blue-700">
            <input
              ref={importInputRef}
              type="file"
              accept=".csv,.xlsx"
              className="hidden"
              onChange={(event) => {
                const nextFile = event.target.files?.[0] ?? null;
                setImportFile(nextFile);
                setPreview(null);
                setMessage(nextFile ? `Selected file: ${nextFile.name}` : null);
              }}
            />
            Choose file
          </label>
        </div>

        {importFile && (
          <div className="mt-3 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-2 text-[11px] text-slate-600">
              <span>Selected file: {importFile.name}</span>
              <button
                type="button"
                onClick={clearImportSelection}
                className="font-semibold text-slate-700 underline hover:text-slate-900"
              >
                Remove
              </button>
            </div>
            <div className="flex items-center gap-2">
              <button type="button" onClick={handlePreviewImport} disabled={previewing || !sectionId} className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50">
                {previewing ? 'Previewing...' : 'Preview Import'}
              </button>
            </div>
          </div>
        )}

        {preview && (
          <div className="mt-3 rounded-md border border-slate-200 bg-white p-3 text-[11px] text-slate-600">
            <div className="mb-3 rounded border border-blue-100 bg-blue-50 px-3 py-2">
              <p className="font-semibold text-blue-900">Destination to verify before restoring</p>
              <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1 text-blue-900 md:grid-cols-4">
                <div><dt className="text-blue-600">Batch</dt><dd className="font-medium">{batchName || 'Unknown'}</dd></div>
                <div><dt className="text-blue-600">Department</dt><dd className="font-medium">{departmentName || 'Unknown'}</dd></div>
                <div><dt className="text-blue-600">Year</dt><dd className="font-medium">{yearName || 'Unknown'}</dd></div>
                <div><dt className="text-blue-600">Section</dt><dd className="font-medium">{sectionName || 'Unknown'}</dd></div>
              </dl>
            </div>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
              <div><span className="block text-slate-400 uppercase">Total Rows</span><strong>{preview.total_rows}</strong></div>
              <div><span className="block text-slate-400 uppercase">New Students</span><strong>{preview.new_students}</strong></div>
              <div><span className="block text-slate-400 uppercase">Already Assigned</span><strong>{preview.already_assigned}</strong></div>
              <div><span className="block text-slate-400 uppercase">Eligible for Restoration</span><strong>{preview.eligible_for_restoration}</strong></div>
              <div><span className="block text-slate-400 uppercase">Placement Conflicts</span><strong>{preview.placement_conflicts}</strong></div>
              <div><span className="block text-slate-400 uppercase">Invalid Rows</span><strong>{preview.invalid_rows}</strong></div>
              <div><span className="block text-slate-400 uppercase">Duplicate Registers</span><strong>{duplicateRegisterNumbers.length ? duplicateRegisterNumbers.join(', ') : 'None'}</strong></div>
            </div>

            {identityResolutions.length > 0 && (
              <div className="mt-3 border-t border-slate-200 pt-3">
                <p className="font-semibold text-slate-700 mb-2">Identity resolution summary</p>
                <div className="max-h-56 overflow-y-auto rounded border border-slate-200">
                  <table className="w-full text-left">
                    <thead className="sticky top-0 bg-slate-100 text-slate-700">
                      <tr>
                        <th className="px-2 py-1">Row</th>
                        <th className="px-2 py-1">Register / uploaded name</th>
                        <th className="px-2 py-1">Selected student</th>
                        <th className="px-2 py-1">Other matching IDs</th>
                        <th className="px-2 py-1">Destination / status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                      {identityResolutions.map((resolution) => (
                        <tr key={`${resolution.row_number}-${resolution.register_no}`}>
                          <td className="px-2 py-1">{resolution.row_number}</td>
                          <td className="px-2 py-1">
                            <span className="block font-medium text-slate-700">{resolution.register_no}</span>
                            <span>{resolution.uploaded_name}</span>
                          </td>
                          <td className="px-2 py-1">
                            {resolution.selected_student_id === null
                              ? `Unresolved (candidates: ${(resolution.candidate_student_ids ?? []).join(', ') || 'none'})`
                              : `#${resolution.selected_student_id} — ${resolution.selected_student_name}`}
                          </td>
                          <td className="px-2 py-1">{(resolution.other_student_ids ?? []).join(', ') || 'None'}</td>
                          <td className="px-2 py-1">
                            Section {resolution.destination_section_name || sectionName || 'Unknown'} · {(resolution.resolution_status || 'unknown').replace(/_/g, ' ')}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {previewNotes.length > 0 && (
              <div className="mt-3 border-t border-slate-200 pt-3">
                <p className="font-semibold text-slate-700 mb-2">Validation and placement notes</p>
                <ul className="list-disc pl-4 space-y-1 text-slate-600">
                  {previewNotes.map((error, index) => (
                    <li key={`${error}-${index}`}>{error}</li>
                  ))}
                </ul>
              </div>
            )}

            {preview.section_id === sectionId &&
              preview.invalid_rows === 0 &&
              (preview.new_students > 0 || preview.eligible_for_restoration > 0) && (
                <div className="mt-4 flex justify-end border-t border-slate-200 pt-3">
                  <button
                    type="button"
                    onClick={handleConfirmImport}
                    disabled={importing || previewing}
                    className="rounded-md bg-emerald-600 px-3 py-2 text-[11px] font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
                  >
                    {importing
                      ? 'Processing...'
                      : preview.new_students === 0
                        ? `Restore ${preview.eligible_for_restoration} eligible students`
                        : preview.eligible_for_restoration > 0
                          ? `Import ${preview.new_students} new and restore ${preview.eligible_for_restoration} eligible students`
                          : `Import ${preview.new_students} new students`}
                  </button>
                </div>
              )}
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-[1fr_2fr_auto] gap-2 my-4">
        <input
          required
          minLength={2}
          value={registerNo}
          onChange={(event) => setRegisterNo(event.target.value)}
          placeholder="Register Number"
          aria-label="Register Number"
          className="text-xs border border-slate-300 rounded-md px-2.5 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <input
          required
          minLength={2}
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Student Name"
          aria-label="Student Name"
          className="text-xs border border-slate-300 rounded-md px-2.5 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          type="submit"
          disabled={saving || !sectionId}
          className="bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold px-3 py-2 rounded-md disabled:opacity-50"
        >
          {saving ? 'Adding...' : 'Add Student'}
        </button>
      </form>

      {message && <p className="text-xs text-slate-600 mb-3">{message}</p>}

      <div className="overflow-x-auto border border-slate-200 rounded-md">
        {loading ? (
          <p className="p-4 text-xs text-slate-500">Loading section roster...</p>
        ) : (
          <table className="student-roster-table w-full text-left text-xs">
            <thead className="bg-slate-100 text-slate-700 uppercase text-[11px]">
              <tr>
                <th className="py-2 px-3">Register No</th>
                <th className="py-2 px-3">Student Name</th>
                <th className="py-2 px-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {students.map((student) => (
                <React.Fragment key={student.id || student.registerNo}>
                <tr>
                  {editingStudentId === student.id ? (
                    <>
                      <td className="py-2 px-3 text-slate-500">{student.registerNo}</td>
                      <td className="py-2 px-3">
                        <input
                          required
                          value={editRegisterNo}
                          onChange={(event) => setEditRegisterNo(event.target.value)}
                          aria-label={`Register Number for ${student.name}`}
                          className="mb-1 w-full min-w-32 text-xs border border-slate-300 rounded-md px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                        <input
                          required
                          value={editName}
                          onChange={(event) => setEditName(event.target.value)}
                          aria-label={`Student Name for ${student.registerNo}`}
                          className="w-full min-w-40 text-xs border border-slate-300 rounded-md px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                      </td>
                      <td className="py-2 px-3 whitespace-nowrap">
                        <button type="button" onClick={() => handleSaveEdit(student.id)} disabled={saving} className="mr-2 font-semibold text-blue-700 hover:text-blue-900 disabled:opacity-50">
                          {saving ? 'Saving...' : 'Save'}
                        </button>
                        <button type="button" onClick={cancelEditing} disabled={saving} className="font-semibold text-slate-600 hover:text-slate-900 disabled:opacity-50">
                          Cancel
                        </button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="py-2 px-3 text-slate-500">{student.registerNo}</td>
                      <td className="py-2 px-3">{student.name}</td>
                      <td className="py-2 px-3 whitespace-nowrap">
                        <button type="button" onClick={() => startEditing(student)} disabled={editingStudentId !== null || deletingStudentId !== null || archivingAll} className="mr-3 font-semibold text-blue-700 hover:text-blue-900 disabled:opacity-50">
                          Edit
                        </button>
                        <button type="button" onClick={() => handleDelete(student)} disabled={editingStudentId !== null || deletingStudentId !== null || archivingAll} className="font-semibold text-red-700 hover:text-red-900 disabled:opacity-50">
                          {deletingStudentId === student.id ? 'Deleting...' : 'Delete'}
                        </button>
                      </td>
                    </>
                  )}
                </tr>
                </React.Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showArchivedStudents && (
        <div className="mt-4 border-t border-slate-200 pt-3">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-700">Archived Students</h3>
            <button
              type="button"
              onClick={handlePermanentlyDeleteArchived}
              disabled={archivedLoading || permanentlyDeletingArchived || permanentlyDeletingStudentId !== null || archivedStudents.length === 0}
              className="text-xs font-semibold text-red-700 hover:text-red-900 disabled:opacity-50"
            >
              {permanentlyDeletingArchived ? 'Deleting...' : 'Remove All'}
            </button>
          </div>
          {archivedLoading ? (
            <p className="text-xs text-slate-500">Loading archived students...</p>
          ) : archivedStudents.length === 0 ? (
            <p className="text-xs text-slate-500">No archived students in this section.</p>
          ) : (
            <div className="overflow-x-auto rounded-md border border-slate-200">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-100 text-[11px] uppercase text-slate-700">
                  <tr>
                    <th className="px-3 py-2">Register No</th>
                    <th className="px-3 py-2">Student Name</th>
                    <th className="px-3 py-2">Section</th>
                    <th className="px-3 py-2">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {archivedStudents.map((student) => (
                    <tr key={student.id}>
                      <td className="px-3 py-2 text-slate-500">{student.registerNo}</td>
                      <td className="px-3 py-2">{student.name}</td>
                      <td className="px-3 py-2">{sectionName ? `Section ${sectionName}` : '-'}</td>
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          onClick={() => handleRestore(student)}
                          disabled={restoringStudentId !== null || deletingStudentId !== null || permanentlyDeletingArchived || permanentlyDeletingStudentId !== null}
                          className="font-semibold text-blue-700 hover:text-blue-900 disabled:opacity-50"
                        >
                          {restoringStudentId === student.id ? 'Restoring...' : 'Restore'}
                        </button>
                        <button
                          type="button"
                          onClick={() => handlePermanentlyDeleteArchivedStudent(student)}
                          disabled={restoringStudentId !== null || permanentlyDeletingArchived || permanentlyDeletingStudentId !== null}
                          className="font-semibold text-red-700 hover:text-red-900 disabled:opacity-50"
                        >
                          {permanentlyDeletingStudentId === student.id ? 'Deleting...' : 'Delete'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
        </>
      )}
    </section>
  );
};

interface StudentManagementErrorBoundaryState {
  error: Error | null;
}

class StudentManagementErrorBoundary extends React.Component<
  { children: React.ReactNode },
  StudentManagementErrorBoundaryState
> {
  state: StudentManagementErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): StudentManagementErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Student management rendering failed.', error, errorInfo);
  }

  render() {
    if (this.state.error) {
      return (
        <section role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-900">
          <h2 className="font-semibold">Student management could not be displayed</h2>
          <p className="mt-1">An unexpected rendering error occurred. Reload the page to try again.</p>
          <p className="mt-1 text-xs">{this.state.error.message}</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-3 rounded border border-red-300 bg-white px-3 py-1.5 text-xs font-semibold hover:bg-red-100"
          >
            Reload page
          </button>
        </section>
      );
    }

    return this.props.children;
  }
}

export const StudentManagement: React.FC<StudentManagementProps> = (props) => (
  <StudentManagementErrorBoundary>
    <StudentManagementContent {...props} />
  </StudentManagementErrorBoundary>
);
