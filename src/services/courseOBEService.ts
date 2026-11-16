import { apiUrl } from '../config';

export type COPOMappingValues = Array<Array<number | null>>;

interface COPOMappingResponse {
  subject_id: number;
  section_id: number;
  values: COPOMappingValues;
}

async function throwMappingError(response: Response, fallback: string): Promise<never> {
  const payload = await response.json().catch(() => null);
  throw new Error(payload?.detail || `${fallback} (${response.status}).`);
}

export async function loadCourseCOPOMapping(subjectId: number, sectionId: number): Promise<COPOMappingValues> {
  const response = await fetch(apiUrl(`/api/course-obe/subjects/${subjectId}/co-po-mapping?section_id=${sectionId}`));
  if (!response.ok) await throwMappingError(response, 'Unable to load CO–PO mapping');
  const payload = await response.json() as COPOMappingResponse;
  return payload.values;
}

export async function saveCourseCOPOMapping(
  subjectId: number,
  sectionId: number,
  values: COPOMappingValues,
): Promise<COPOMappingValues> {
  const response = await fetch(apiUrl(`/api/course-obe/subjects/${subjectId}/co-po-mapping?section_id=${sectionId}`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ values }),
  });
  if (!response.ok) await throwMappingError(response, 'Unable to save CO–PO mapping');
  const payload = await response.json() as COPOMappingResponse;
  return payload.values;
}