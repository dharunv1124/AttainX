import { Batch, Department, Section, Semester, Year } from '../types';
import { apiUrl } from '../config';

export interface DeletionStatus {
  can_delete: boolean;
  reason: string | null;
}

export interface SectionDeletionStatus extends DeletionStatus {
  student_count: number;
  placement_count: number;
  student_mark_count: number;
  exam_count: number;
  exam_question_count: number;
  exam_covered_co_count: number;
  course_co_po_mapping_count: number;
  course_co_attainment_input_count: number;
  student_ids_to_delete: number[];
  student_ids_preserved: number[];
  plan_token: string;
}

async function loadList<T>(path: string): Promise<T[]> {
  const response = await fetch(apiUrl(path));
  if (!response.ok) {
    throw new Error(`Unable to load academic data (${response.status}).`);
  }
  const data = await response.json();
  return Array.isArray(data) ? data : [];
}

export async function loadDepartments(): Promise<Department[]> {
  return loadList<any>('/api/departments').then((items) => items.map((item) => ({
    id: Number(item.id),
    name: item.name,
    code: item.code,
  })));
}

export async function loadBatches(): Promise<Batch[]> {
  return loadList<any>('/api/academic/batches').then((items) => items
    .filter((item) => item.is_active ?? item.isActive)
    .map((item) => ({
      id: Number(item.id),
      batchName: item.batch_name ?? item.batchName,
      startYear: Number(item.start_year ?? item.startYear),
      endYear: Number(item.end_year ?? item.endYear),
      isActive: Boolean(item.is_active ?? item.isActive),
      isDefault: Boolean(item.is_default ?? item.isDefault),
    })));
}

export async function createBatch(batchName: string): Promise<Batch> {
  const response = await fetch(apiUrl('/api/academic/batches'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ batch_name: batchName, is_active: true }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Unable to add academic batch.');
  return {
    id: Number(data.id),
    batchName: data.batch_name,
    startYear: Number(data.start_year),
    endYear: Number(data.end_year),
    isActive: Boolean(data.is_active),
    isDefault: Boolean(data.is_default),
  };
}

export async function getBatchDeletionStatus(batchId: number): Promise<DeletionStatus> {
  const response = await fetch(apiUrl(`/api/academic/batches/${batchId}/deletion-status`));
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Unable to check batch data.');
  return data as DeletionStatus;
}

export async function deleteBatch(batchId: number): Promise<void> {
  const response = await fetch(apiUrl(`/api/academic/batches/${batchId}`), { method: 'DELETE' });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Unable to delete batch (HTTP ${response.status}).`);
  }
}

export async function loadYears(): Promise<Year[]> {
  return loadList<any>('/api/academic/years').then((items) => items.map((item) => ({
    id: Number(item.id),
    yearNumber: Number(item.year_number ?? item.yearNumber),
    name: item.name,
  })));
}

export async function loadSemesters(): Promise<Semester[]> {
  return loadList<any>('/api/academic/semesters').then((items) => items.map((item) => ({
    id: Number(item.id),
    semesterNumber: Number(item.semester_number ?? item.semesterNumber),
    name: item.name,
    yearId: Number(item.year_id ?? item.yearId),
  })));
}

export async function loadSections(
  departmentId?: number,
  yearId?: number,
  batchId?: number,
): Promise<Section[]> {
  const params = new URLSearchParams();
  if (departmentId) params.set('department_id', String(departmentId));
  if (yearId) params.set('year_id', String(yearId));
  if (batchId) params.set('batch_id', String(batchId));
  const query = params.toString();
  return loadList<any>(`/api/academic/sections${query ? `?${query}` : ''}`).then((items) => items.map((item) => ({
    id: Number(item.id),
    name: item.name,
    batchId: Number(item.batch_id ?? item.batchId),
    departmentId: Number(item.department_id ?? item.departmentId),
    departmentCode: item.department_code ?? item.departmentCode,
    yearId: Number(item.year_id ?? item.yearId),
    yearName: item.year_name ?? item.yearName,
  })));
}

function mapSection(item: any): Section {
  return {
    id: Number(item.id),
    name: item.name,
    batchId: Number(item.batch_id ?? item.batchId),
    departmentId: Number(item.department_id ?? item.departmentId),
    departmentCode: item.department_code ?? item.departmentCode,
    yearId: Number(item.year_id ?? item.yearId),
    yearName: item.year_name ?? item.yearName,
  };
}

export async function createSection(departmentId: number, yearId: number, batchId: number, name: string): Promise<Section> {
  const response = await fetch(apiUrl('/api/academic/sections'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, batch_id: batchId, department_id: departmentId, year_id: yearId }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Unable to add section.');
  return mapSection(data);
}

export async function deleteSection(sectionId: number, planToken: string): Promise<void> {
  const response = await fetch(
    apiUrl(`/api/academic/sections/${sectionId}?plan_token=${encodeURIComponent(planToken)}`),
    { method: 'DELETE' },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Unable to remove section (HTTP ${response.status}).`);
  }
}

export async function getSectionDeletionStatus(sectionId: number): Promise<SectionDeletionStatus> {
  const response = await fetch(apiUrl(`/api/academic/sections/${sectionId}/deletion-status`));
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Unable to check section data.');
  const countFields = [
    'student_count',
    'placement_count',
    'student_mark_count',
    'exam_count',
    'exam_question_count',
    'exam_covered_co_count',
    'course_co_po_mapping_count',
    'course_co_attainment_input_count',
  ];
  if (
    countFields.some((field) => !Number.isInteger(data[field]) || data[field] < 0) ||
    !Array.isArray(data.student_ids_to_delete) ||
    !data.student_ids_to_delete.every((id: unknown) => Number.isInteger(id) && Number(id) > 0) ||
    !Array.isArray(data.student_ids_preserved) ||
    !data.student_ids_preserved.every((id: unknown) => Number.isInteger(id) && Number(id) > 0) ||
    typeof data.plan_token !== 'string' ||
    !data.plan_token
  ) {
    throw new Error(
      'The backend does not provide the detailed Section deletion preview. Restart the backend before deleting a Section.',
    );
  }
  return data as SectionDeletionStatus;
}
