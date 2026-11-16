import { Subject } from '../types';
import { apiUrl } from '../config';

export async function loadSubjects(
  departmentId: number,
  yearId: number,
  semesterId: number,
  includeInactive = false,
  batchId?: number,
): Promise<Subject[]> {
  const params = new URLSearchParams({
    department_id: String(departmentId),
    year_id: String(yearId),
    semester_id: String(semesterId),
  });
  if (batchId !== undefined) params.set('batch_id', String(batchId));
  if (includeInactive) params.set('include_inactive', 'true');
  const response = await fetch(apiUrl(`/api/subjects?${params.toString()}`));
  if (!response.ok) throw new Error(`Unable to load subjects (${response.status}).`);
  const data = await response.json();
  return Array.isArray(data)
    ? data.map((subject: { id: number; name: string; batch_id: number; is_active: boolean }) => ({
        id: subject.id,
        name: subject.name,
        batchId: subject.batch_id,
        isActive: subject.is_active,
      }))
    : [];
}

export async function createSubject(
  name: string,
  departmentId: number,
  yearId: number,
  semesterId: number,
  batchId?: number,
): Promise<void> {
  const response = await fetch(apiUrl('/api/subjects'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name,
      batch_id: batchId,
      department_id: departmentId,
      year_id: yearId,
      semester_id: semesterId,
    }),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail || `Unable to add subject (${response.status}).`);
  }
}

export async function removeSubject(subjectId: number): Promise<void> {
  const response = await fetch(apiUrl(`/api/subjects/${subjectId}`), { method: 'DELETE' });
  if (!response.ok) throw new Error(`Unable to remove subject (${response.status}).`);
}

export async function permanentlyDeleteArchivedSubject(subjectId: number): Promise<void> {
  const response = await fetch(apiUrl(`/api/subjects/${subjectId}/permanent`), { method: 'DELETE' });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Unable to permanently delete subject (${response.status}).`);
  }
}

export async function restoreSubject(
  subjectId: number,
  departmentId: number,
  yearId: number,
  semesterId: number,
  batchId?: number,
): Promise<void> {
  const params = new URLSearchParams({
    department_id: String(departmentId),
    year_id: String(yearId),
    semester_id: String(semesterId),
  });
  if (batchId !== undefined) params.set('batch_id', String(batchId));
  const response = await fetch(apiUrl(`/api/subjects/${subjectId}/restore?${params.toString()}`), {
    method: 'POST',
  });
  if (!response.ok) throw new Error(`Unable to recover subject (${response.status}).`);
}