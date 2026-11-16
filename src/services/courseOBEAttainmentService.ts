import { apiUrl } from '../config';
import { loadExamsFromApi } from './examService';
import {
  buildCourseExamAttainmentDefaults,
  type CourseCOAttainmentInputRow,
  type CourseExamAttainmentDefaults,
} from './courseOBEAttainmentDefaults';

export type { CourseCOAttainmentInputRow } from './courseOBEAttainmentDefaults';

export interface CourseCOAttainmentResultRow {
  average: number | null;
  attainment: number | null;
  university_attainment: number | null;
  d: number | null;
  e: number | null;
  f: number | null;
  ninety_percent_f: number | null;
  ten_percent_g: number | null;
  overall_co: number | null;
}

export interface CourseCOAttainmentResponse {
  subject_id: number;
  section_id: number;
  inputs: CourseCOAttainmentInputRow[];
  results: CourseCOAttainmentResultRow[];
}

export type { CourseExamAttainmentDefaults } from './courseOBEAttainmentDefaults';

export interface CoursePOAttainmentResponse {
  subject_id: number;
  section_id: number;
  values: Array<Array<number | null>>;
  overall_values: Array<number | null>;
}

async function throwAttainmentError(response: Response, fallback: string): Promise<never> {
  const payload = await response.json().catch(() => null);
  throw new Error(payload?.detail || `${fallback} (${response.status}).`);
}

export async function loadCourseExamAttainmentDefaults(
  departmentId: number,
  yearId: number,
  semesterId: number,
  sectionId: number,
  subjectId: number,
  batchId: number,
): Promise<CourseExamAttainmentDefaults> {
  const exams = await loadExamsFromApi({
    batchId,
    departmentId,
    yearId,
    semesterId,
    sectionId,
    subjectId,
  });

  const matchingExams = exams.filter((exam) =>
    exam.departmentId === departmentId
    && exam.yearId === yearId
    && exam.semesterId === semesterId
    && exam.sectionId === sectionId
    && exam.subjectId === subjectId
    && [
      'INTERNAL_1',
      'AUTONOMOUS_INTERNAL_1',
      'INTERNAL_2',
      'AUTONOMOUS_INTERNAL_2',
      'MODEL',
      'AUTONOMOUS_MODEL',
    ].includes(exam.examType)
  );

  const calculationsByExamId: Record<number, unknown> = {};
  await Promise.all(matchingExams.map(async (exam) => {
    const response = await fetch(apiUrl(`/api/exams/${exam.id}/marks`));
    if (!response.ok) await throwAttainmentError(response, `Unable to load ${exam.name} CO results`);
    const payload = await response.json();
    calculationsByExamId[exam.id] = payload.calculation_result ?? payload.calculationResult;
  }));

  return buildCourseExamAttainmentDefaults(
    exams,
    { departmentId, yearId, semesterId, sectionId, subjectId },
    calculationsByExamId,
  );
}

export async function loadCourseOverallCOAttainment(
  subjectId: number,
  sectionId: number,
): Promise<CourseCOAttainmentResponse> {
  const response = await fetch(apiUrl(`/api/course-obe/subjects/${subjectId}/overall-co-attainment?section_id=${sectionId}`));
  if (!response.ok) await throwAttainmentError(response, 'Unable to load course CO attainment');
  return await response.json() as CourseCOAttainmentResponse;
}

export async function loadCoursePOAttainment(subjectId: number, sectionId: number): Promise<CoursePOAttainmentResponse> {
  const response = await fetch(apiUrl(`/api/course-obe/subjects/${subjectId}/po-attainment?section_id=${sectionId}`));
  if (!response.ok) await throwAttainmentError(response, 'Unable to load PO attainment');
  return await response.json() as CoursePOAttainmentResponse;
}

export async function saveCourseOverallCOAttainment(
  subjectId: number,
  sectionId: number,
  inputs: CourseCOAttainmentInputRow[],
): Promise<CourseCOAttainmentResponse> {
  const response = await fetch(apiUrl(`/api/course-obe/subjects/${subjectId}/overall-co-attainment?section_id=${sectionId}`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ inputs }),
  });
  if (!response.ok) await throwAttainmentError(response, 'Unable to save course CO attainment');
  return await response.json() as CourseCOAttainmentResponse;
}