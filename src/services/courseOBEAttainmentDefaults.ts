import type { ExamDetail } from '../types';

export interface CourseCOAttainmentInputRow {
  a: number | null;
  b: number | null;
  c: number | null;
  university: number | null;
  g: number | null;
}

const COURSE_OUTCOMES = Array.from({ length: 5 }, (_, index) => `CO${index + 1}`);

export type CourseExamInputKey = 'a' | 'b' | 'c';
export type CourseExamAttainmentDefaults = Record<CourseExamInputKey, Array<number | null>>;

const EXAM_INPUT_TYPES: Array<{
  key: keyof CourseExamAttainmentDefaults;
  examTypes: string[];
}> = [
  { key: 'a', examTypes: ['INTERNAL_1', 'AUTONOMOUS_INTERNAL_1'] },
  { key: 'b', examTypes: ['INTERNAL_2', 'AUTONOMOUS_INTERNAL_2'] },
  { key: 'c', examTypes: ['MODEL', 'AUTONOMOUS_MODEL'] },
];

export interface CourseExamContext {
  departmentId: number;
  yearId: number;
  semesterId: number;
  sectionId: number;
  subjectId: number;
}

type ExamCOAttainment = {
  attainment_percentage?: number | null;
  attainmentPercentage?: number | null;
};

type ExamCalculation = {
  overall_co_attainment?: Record<string, ExamCOAttainment>;
  overallCOAttainment?: Record<string, ExamCOAttainment>;
};

const isExamCalculation = (value: unknown): value is ExamCalculation =>
  value !== null && typeof value === 'object';

export function buildCourseExamAttainmentDefaults(
  exams: ExamDetail[],
  context: CourseExamContext,
  calculationsByExamId: Record<number, unknown>,
): CourseExamAttainmentDefaults {
  const defaults: CourseExamAttainmentDefaults = {
    a: COURSE_OUTCOMES.map(() => null),
    b: COURSE_OUTCOMES.map(() => null),
    c: COURSE_OUTCOMES.map(() => null),
  };
  const scopedExams = exams.filter((exam) =>
    exam.departmentId === context.departmentId
    && exam.yearId === context.yearId
    && exam.semesterId === context.semesterId
    && exam.sectionId === context.sectionId
    && exam.subjectId === context.subjectId
  );

  for (const { key, examTypes } of EXAM_INPUT_TYPES) {
    const exam = scopedExams.find((candidate) => examTypes.includes(candidate.examType));
    if (!exam) continue;

    const calculation = calculationsByExamId[exam.id];
    if (!isExamCalculation(calculation)) continue;
    const overallResults = calculation.overall_co_attainment ?? calculation.overallCOAttainment;
    if (!overallResults) continue;

    const configuredCOs = new Set(exam.coveredCOs.map((co) => co.trim().toUpperCase()));
    for (const [rowIndex, outcome] of COURSE_OUTCOMES.entries()) {
      if (!configuredCOs.has(outcome)) continue;
      const result = overallResults[outcome] ?? overallResults[outcome.toLowerCase()];
      const percentage = result?.attainment_percentage ?? result?.attainmentPercentage;
      if (typeof percentage === 'number' && Number.isFinite(percentage)) {
        defaults[key][rowIndex] = percentage;
      }
    }
  }

  return defaults;
}

export function mergeCourseExamAttainmentDefaults(
  inputs: CourseCOAttainmentInputRow[],
  defaults: CourseExamAttainmentDefaults,
): CourseCOAttainmentInputRow[] {
  return inputs.map((input, rowIndex) => ({
    ...input,
    a: input.a ?? defaults.a[rowIndex] ?? null,
    b: input.b ?? defaults.b[rowIndex] ?? null,
    c: input.c ?? defaults.c[rowIndex] ?? null,
  }));
}
