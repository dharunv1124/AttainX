import { Student, StudentImportIdentityResolution, StudentImportPreview, StudentImportResult } from '../types';
import { apiUrl } from '../config';
import { buildStudentImportFormData } from './studentImportForm';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readCount(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
    throw new Error(
      `The student preview response is missing a valid "${field}" count. Update or restart the backend, then retry Preview Import.`,
    );
  }
  return value;
}

function readStringArray(value: unknown, field: string): string[] {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value) || !value.every((item) => typeof item === 'string')) {
    throw new Error(`Student import preview returned an invalid "${field}" list.`);
  }
  return value;
}

function readIdArray(value: unknown, field: string): number[] {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value) || !value.every((item) => typeof item === 'number' && Number.isInteger(item))) {
    throw new Error(`Student import preview returned an invalid "${field}" list.`);
  }
  return value;
}

function parseIdentityResolutions(value: unknown): StudentImportIdentityResolution[] {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value)) {
    throw new Error('Student import preview returned an invalid identity resolution list.');
  }

  return value.map((item, index) => {
    if (!isRecord(item)) {
      throw new Error(`Student import preview returned an invalid identity resolution at item ${index + 1}.`);
    }

    const selectedId = item.selected_student_id;
    const selectedName = item.selected_student_name;
    if (
      typeof item.row_number !== 'number' ||
      !Number.isInteger(item.row_number) ||
      typeof item.register_no !== 'string' ||
      typeof item.uploaded_name !== 'string' ||
      (selectedId !== null && (typeof selectedId !== 'number' || !Number.isInteger(selectedId))) ||
      (selectedName !== null && typeof selectedName !== 'string') ||
      typeof item.resolution_status !== 'string' ||
      typeof item.destination_section_id !== 'number' ||
      !Number.isInteger(item.destination_section_id) ||
      typeof item.destination_section_name !== 'string'
    ) {
      throw new Error(`Student import preview returned incomplete identity details at item ${index + 1}.`);
    }

    return {
      row_number: item.row_number,
      register_no: item.register_no,
      uploaded_name: item.uploaded_name,
      selected_student_id: selectedId,
      selected_student_name: selectedName,
      candidate_student_ids: readIdArray(item.candidate_student_ids, 'candidate student IDs'),
      other_student_ids: readIdArray(item.other_student_ids, 'other student IDs'),
      resolution_status: item.resolution_status,
      destination_section_id: item.destination_section_id,
      destination_section_name: item.destination_section_name,
    };
  });
}

function parseStudentImportPreview(value: unknown): StudentImportPreview {
  if (!isRecord(value)) {
    throw new Error('The student import preview response was not a valid object.');
  }

  for (const field of ['section_id', 'batch_id', 'total_rows', 'valid_rows', 'invalid_rows'] as const) {
    if (typeof value[field] !== 'number' || !Number.isInteger(value[field]) || value[field] < 0) {
      throw new Error(`Student import preview response is missing a valid "${field}" value.`);
    }
  }

  const counts = {
    new_students: readCount(value.new_students, 'new_students'),
    already_assigned: readCount(value.already_assigned, 'already_assigned'),
    eligible_for_restoration: readCount(value.eligible_for_restoration, 'eligible_for_restoration'),
    placement_conflicts: readCount(value.placement_conflicts, 'placement_conflicts'),
  };
  if (!Array.isArray(value.identity_resolutions)) {
    throw new Error(
      'The student preview response is missing identity resolution details. Update or restart the backend, then retry Preview Import.',
    );
  }
  const identityResolutions = parseIdentityResolutions(value.identity_resolutions);
  const errors = readStringArray(value.errors, 'errors');
  const sectionId = value.section_id as number;
  const batchId = value.batch_id as number;
  const totalRows = value.total_rows as number;
  const validRows = value.valid_rows as number;
  const invalidRows = value.invalid_rows as number;

  return {
    section_id: sectionId,
    batch_id: batchId,
    total_rows: totalRows,
    valid_rows: validRows,
    invalid_rows: invalidRows,
    ...counts,
    duplicate_register_numbers: readStringArray(
      value.duplicate_register_numbers,
      'duplicate_register_numbers',
    ),
    identity_resolutions: identityResolutions,
    errors,
  };
}

function mapStudent(value: any): Student {
  return {
    id: Number(value.id),
    registerNo: value.register_no || value.registerNo,
    name: value.name,
    sectionId: Number(value.section_id || value.sectionId),
    batchId: Number(value.batch_id ?? value.batchId),
    archivedAt: value.archived_at ?? null,
  };
}

export async function loadSectionStudents(sectionId: number, includeArchived = false): Promise<Student[]> {
  const archivedQuery = includeArchived ? '?include_archived=true' : '';
  const response = await fetch(apiUrl(`/api/sections/${sectionId}/students${archivedQuery}`));
  if (!response.ok) {
    throw new Error(`Unable to load section roster (${response.status}).`);
  }
  const data = await response.json();
  return Array.isArray(data) ? data.map(mapStudent) : [];
}

export async function addStudent(registerNo: string, name: string, sectionId: number, semesterId: number): Promise<Student> {
  const response = await fetch(apiUrl('/api/students'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ register_no: registerNo, name, section_id: sectionId, semester_id: semesterId }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Unable to add student.');
  return mapStudent(data);
}

export async function updateStudent(studentId: number, registerNo: string, name: string): Promise<Student> {
  const response = await fetch(apiUrl(`/api/students/${studentId}`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ register_no: registerNo.trim(), name: name.trim() }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Unable to update student.');
  return mapStudent(data);
}

export async function moveStudentPlacement(
  studentId: number,
  sectionId: number,
  semesterId: number,
): Promise<Student> {
  const response = await fetch(apiUrl(`/api/students/${studentId}/placement`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ section_id: sectionId, semester_id: semesterId }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Unable to update student placement.');
  return mapStudent(data);
}

export async function deleteStudent(studentId: number): Promise<void> {
  const response = await fetch(apiUrl(`/api/students/${studentId}`), { method: 'DELETE' });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || 'Unable to delete student.');
  }
}

export async function restoreStudent(studentId: number): Promise<Student> {
  const response = await fetch(apiUrl(`/api/students/${studentId}/restore`), { method: 'POST' });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Unable to restore student.');
  return mapStudent(data);
}

export async function permanentlyDeleteArchivedStudents(sectionId: number): Promise<number> {
  const response = await fetch(apiUrl(`/api/sections/${sectionId}/students/archived`), { method: 'DELETE' });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Unable to permanently delete archived students.');
  return Number(data.deleted_count ?? 0);
}

export async function permanentlyDeleteArchivedStudent(studentId: number): Promise<void> {
  const response = await fetch(apiUrl(`/api/students/${studentId}/permanent`), { method: 'DELETE' });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Unable to permanently delete archived student.');
}

export async function previewStudentImport(sectionId: number, file: File, semesterId: number): Promise<StudentImportPreview> {
  const formData = buildStudentImportFormData(sectionId, file, false, semesterId);

  const response = await fetch(apiUrl('/api/students/import-preview'), {
    method: 'POST',
    body: formData,
  });

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new Error('The student import preview returned an unreadable response. Please retry.');
  }
  if (!response.ok) {
    const detail = isRecord(data) && typeof data.detail === 'string'
      ? data.detail
      : `Unable to preview the student roster import (HTTP ${response.status}).`;
    throw new Error(detail);
  }

  return parseStudentImportPreview(data);
}

export async function importStudentList(sectionId: number, file: File, semesterId: number): Promise<StudentImportResult> {
  const formData = buildStudentImportFormData(sectionId, file, true, semesterId);

  const response = await fetch(apiUrl('/api/students/import'), {
    method: 'POST',
    body: formData,
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : 'Unable to import the student roster.';
    throw new Error(detail);
  }

  return data as StudentImportResult;
}
