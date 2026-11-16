import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { ExamDetail } from '../types';
import {
  buildCourseExamAttainmentDefaults,
  mergeCourseExamAttainmentDefaults,
  type CourseCOAttainmentInputRow,
  type CourseExamAttainmentDefaults,
} from './courseOBEAttainmentDefaults';

const emptyInputs = (): CourseCOAttainmentInputRow[] =>
  Array.from({ length: 5 }, () => ({
    a: null,
    b: null,
    c: null,
    university: null,
    g: null,
  }));

const exam = (
  id: number,
  examType: ExamDetail['examType'],
  sectionId = 7,
  coveredCOs = ['CO1', 'CO2'],
): ExamDetail => ({
  id,
  name: `Exam ${id}`,
  examDate: null,
  examType,
  batchId: 1,
  departmentId: 1,
  yearId: 3,
  semesterId: 5,
  sectionId,
  subjectId: 11,
  passPercentage: 50,
  coveredCOs,
  questions: [],
  departmentName: 'Department',
  departmentCode: 'DPT',
  yearName: '3rd Year',
  semesterName: 'Semester 5',
  sectionName: 'A',
  subjectName: 'Subject',
  totalMarks: 0,
  totalQuestions: 0,
  studentCount: 0,
  createdAt: '',
  updatedAt: '',
});

test('exam defaults use exact context, saved CO coverage, and existing calculated percentages', () => {
  const defaults = buildCourseExamAttainmentDefaults(
    [
      exam(101, 'INTERNAL_1', 7, ['CO1', 'CO2']),
      exam(102, 'INTERNAL_2', 7, ['CO2', 'CO3']),
      exam(103, 'MODEL', 7, ['CO1', 'CO2', 'CO3', 'CO4', 'CO5']),
      exam(999, 'INTERNAL_1', 8, ['CO1']),
    ],
    { departmentId: 1, yearId: 3, semesterId: 5, sectionId: 7, subjectId: 11 },
    {
      101: {
        overall_co_attainment: {
          CO1: { attainment_percentage: 75 },
          CO2: { attainment_percentage: 0 },
          CO3: { attainment_percentage: 90 },
        },
      },
      102: null,
      103: {
        overall_co_attainment: {
          CO1: { attainment_percentage: 20 },
          CO2: { attainment_percentage: 40 },
          CO3: { attainment_percentage: 60 },
          CO4: { attainment_percentage: 80 },
          CO5: { attainment_percentage: 100 },
        },
      },
      999: {
        overall_co_attainment: {
          CO1: { attainment_percentage: 99 },
        },
      },
    },
  );

  assert.deepEqual(defaults.a, [75, 0, null, null, null]);
  assert.deepEqual(defaults.b, [null, null, null, null, null]);
  assert.deepEqual(defaults.c, [20, 40, 60, 80, 100]);
});

test('exam defaults fill only blank A/B/C values and retain saved overrides', () => {
  const defaults: CourseExamAttainmentDefaults = {
    a: [70, 60, 50, 40, 30],
    b: [71, 61, 51, 41, 31],
    c: [72, 62, 52, 42, 32],
  };
  const inputs = emptyInputs();
  inputs[0] = { ...inputs[0], a: 12, b: 13, c: 14, university: 15, g: 16 };
  inputs[1] = { ...inputs[1], a: null, b: 0, c: null };

  const merged = mergeCourseExamAttainmentDefaults(inputs, defaults);

  assert.deepEqual(
    merged.map(({ a, b, c }) => [a, b, c]),
    [
      [12, 13, 14],
      [60, 0, 62],
      [50, 51, 52],
      [40, 41, 42],
      [30, 31, 32],
    ],
  );
  assert.equal(merged[0].university, 15);
  assert.equal(merged[0].g, 16);
});
