import { Department, Year, Semester, Student, ExamDetail } from '../types';

export const INITIAL_DEPARTMENTS: Department[] = [
  { id: 1, name: 'Computer Science and Engineering', code: 'CSE' },
  { id: 2, name: 'Information Technology', code: 'IT' },
];

export const INITIAL_YEARS: Year[] = [
  { id: 1, yearNumber: 1, name: '1st Year' },
  { id: 2, yearNumber: 2, name: '2nd Year' },
  { id: 3, yearNumber: 3, name: '3rd Year' },
  { id: 4, yearNumber: 4, name: '4th Year' },
];

export const INITIAL_SEMESTERS: Semester[] = [
  { id: 1, semesterNumber: 1, name: 'Semester 1', yearId: 1 },
  { id: 2, semesterNumber: 2, name: 'Semester 2', yearId: 1 },
  { id: 3, semesterNumber: 3, name: 'Semester 3', yearId: 2 },
  { id: 4, semesterNumber: 4, name: 'Semester 4', yearId: 2 },
  { id: 5, semesterNumber: 5, name: 'Semester 5', yearId: 3 },
  { id: 6, semesterNumber: 6, name: 'Semester 6', yearId: 3 },
  { id: 7, semesterNumber: 7, name: 'Semester 7', yearId: 4 },
  { id: 8, semesterNumber: 8, name: 'Semester 8', yearId: 4 },
];

export const INITIAL_STUDENTS: Student[] = [];

export const INITIAL_EXAMS: ExamDetail[] = [
  {
    id: 1,
    name: 'Internal Assessment 1',
    examDate: null,
    examType: 'INTERNAL_1',
    batchId: 1,
    departmentId: 1,
    yearId: 3,
    semesterId: 6,
    sectionId: 1,
    subjectId: 1,
    passPercentage: 50.0,
    coveredCOs: ['CO1', 'CO2'],
    questions: [
      { questionNumber: 'Q1', maxMarks: 2.0, coCode: 'CO1' },
      { questionNumber: 'Q2', maxMarks: 2.0, coCode: 'CO1' },
      { questionNumber: 'Q3', maxMarks: 2.0, coCode: 'CO1' },
      { questionNumber: 'Q4', maxMarks: 2.0, coCode: 'CO1' },
      { questionNumber: 'Q5', maxMarks: 2.0, coCode: 'CO1' },
      { questionNumber: 'Q6', maxMarks: 2.0, coCode: 'CO2' },
      { questionNumber: 'Q7', maxMarks: 2.0, coCode: 'CO2' },
      { questionNumber: 'Q8', maxMarks: 2.0, coCode: 'CO2' },
      { questionNumber: 'Q9', maxMarks: 2.0, coCode: 'CO2' },
      { questionNumber: 'Q10', maxMarks: 2.0, coCode: 'CO2' },
      { questionNumber: 'Q11', maxMarks: 10.0, coCode: 'CO1' },
      { questionNumber: 'Q12', maxMarks: 10.0, coCode: 'CO2' },
      { questionNumber: 'Q13', maxMarks: 10.0, coCode: 'CO1' },
    ],
    departmentName: 'Computer Science and Engineering',
    departmentCode: 'CSE',
    yearName: '3rd Year',
    semesterName: 'Semester 6',
    sectionName: 'A',
    subjectName: 'DATABASE MANAGEMENT SYSTEMS',
    totalMarks: 50.0,
    totalQuestions: 13,
    studentCount: 5,
    createdAt: '2026-09-24T06:30:00Z',
    updatedAt: '2026-09-24T06:30:00Z',
  },
];
