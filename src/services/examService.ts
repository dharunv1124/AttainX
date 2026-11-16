import { ExamDetail, ExamQuestionConfig, ExamType } from '../types';
import { apiUrl } from '../config';

export class ExamValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ExamValidationError';
  }
}

export interface ExamContextFilter {
  batchId?: number;
  departmentId?: number;
  yearId?: number;
  semesterId?: number;
  sectionId?: number;
  subjectId?: number;
}

export async function loadExamsFromApi(context?: ExamContextFilter): Promise<ExamDetail[]> {
  const params = new URLSearchParams();
  if (context?.batchId !== undefined) params.set('batch_id', String(context.batchId));
  if (context?.departmentId !== undefined) params.set('department_id', String(context.departmentId));
  if (context?.yearId !== undefined) params.set('year_id', String(context.yearId));
  if (context?.semesterId !== undefined) params.set('semester_id', String(context.semesterId));
  if (context?.sectionId !== undefined) params.set('section_id', String(context.sectionId));
  if (context?.subjectId !== undefined) params.set('subject_id', String(context.subjectId));
  const query = params.size > 0 ? `?${params.toString()}` : '';
  const response = await fetch(apiUrl(`/api/exams${query}`));
  if (!response.ok) {
    throw new Error(`Unable to load exams (${response.status}).`);
  }

  const data = await response.json();
  return (Array.isArray(data) ? data : []).map(mapApiExam);
}

export async function loadExamById(examId: number): Promise<ExamDetail> {
  const response = await fetch(apiUrl(`/api/exams/${examId}`));
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `Unable to load exam ${examId} (${response.status}).`);
  }
  return mapApiExam(data);
}

export async function loadExamSavedMarkCount(examId: number): Promise<number> {
  const response = await fetch(apiUrl(`/api/exams/${examId}/marks`));
  if (!response.ok) throw new Error(`Unable to verify saved marks (${response.status}).`);
  const data = await response.json();
  const serverMarkCount = Array.isArray(data.marks) ? data.marks.length : 0;
  let localMarkCount = 0;
  try {
    const localMarks = localStorage.getItem(`obe_marks_exam_${examId}`);
    if (localMarks) {
      const parsedMarks = JSON.parse(localMarks);
      localMarkCount = Array.isArray(parsedMarks) ? parsedMarks.length : 1;
    }
  } catch {
    localMarkCount = 1;
  }
  return Math.max(serverMarkCount, localMarkCount);
}

export async function deleteExam(examId: number): Promise<void> {
  const response = await fetch(apiUrl(`/api/exams/${examId}`), { method: 'DELETE' });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ExamValidationError(data.detail || 'Failed to delete exam.');
  }
  try {
    localStorage.removeItem(`obe_marks_exam_${examId}`);
    localStorage.removeItem(`obe_results_exam_${examId}`);
  } catch {
    // The server deletion succeeded; local cache cleanup is best-effort.
  }
}

function mapApiExam(exam: any): ExamDetail {
  return {
    id: Number(exam.id),
    name: exam.name,
    examDate: exam.exam_date ?? exam.examDate ?? null,
    examType: (exam.exam_type || exam.examType || 'CUSTOM') as ExamType,
    batchId: Number(exam.batch_id ?? exam.batchId),
    departmentId: Number(exam.department_id ?? exam.departmentId),
    yearId: Number(exam.year_id ?? exam.yearId),
    semesterId: Number(exam.semester_id ?? exam.semesterId),
    sectionId: Number(exam.section_id ?? exam.sectionId),
    subjectId: Number(exam.subject_id ?? exam.subjectId),
    passPercentage: Number(exam.pass_percentage ?? exam.passPercentage),
    coveredCOs: exam.covered_cos || exam.coveredCOs || [],
    questions: (exam.questions || []).map((question: any): ExamQuestionConfig => ({
      questionId: question.id,
      questionNumber: question.question_number || question.questionNumber,
      maxMarks: Number(question.max_marks ?? question.maxMarks),
      coCode: question.co_code || question.coCode,
    })),
    departmentName: exam.department_name || exam.departmentName,
    departmentCode: exam.department_code || exam.departmentCode,
    yearName: exam.year_name || exam.yearName,
    semesterName: exam.semester_name || exam.semesterName,
    sectionName: exam.section_name || exam.sectionName,
    subjectName: exam.subject_name || exam.subjectName,
    totalMarks: Number(exam.total_marks ?? exam.totalMarks),
    totalQuestions: Number(exam.total_questions ?? exam.totalQuestions),
    studentCount: Number(exam.student_count ?? exam.studentCount),
    createdAt: exam.created_at || exam.createdAt,
    updatedAt: exam.updated_at || exam.updatedAt,
  };
}

export function formatExamDate(examDate: string | null | undefined): string | null {
  if (!examDate) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(examDate.slice(0, 10));
  return match ? `${match[3]}-${match[2]}-${match[1]}` : null;
}

export function validateExamConfiguration(
  name: string,
  examType: ExamType,
  departmentId: number,
  yearId: number,
  semesterId: number,
  sectionId: number,
  subjectId: number,
  passPercentage: number,
  coveredCOs: string[],
  questions: ExamQuestionConfig[]
): void {
  if (!name || !name.trim()) {
    throw new ExamValidationError('Exam Name is required.');
  }

  if (!departmentId || !yearId || !semesterId || !sectionId) {
    throw new ExamValidationError('Please select complete class details (Department, Year, Semester, Section).');
  }

  if (!subjectId) {
    throw new ExamValidationError('Please select a Subject.');
  }

  if (isNaN(passPercentage) || passPercentage <= 0 || passPercentage > 100) {
    throw new ExamValidationError('Pass percentage must be a valid number between 0.01 and 100.');
  }

  const cleanCOs = coveredCOs.map((c) => c.trim().toUpperCase()).filter(Boolean);
  if (cleanCOs.length === 0) {
    throw new ExamValidationError('At least one Course Outcome (CO) must be selected as covered.');
  }

  const uniqueCOs = new Set(cleanCOs);
  if (uniqueCOs.size !== cleanCOs.length) {
    throw new ExamValidationError('Covered COs contain duplicates.');
  }

  if (!questions || questions.length === 0) {
    throw new ExamValidationError('At least one question must be configured for the exam.');
  }

  const seenQ = new Set<string>();
  const mappedCOs = new Set<string>();

  for (let i = 0; i < questions.length; i++) {
    const q = questions[i];
    const qNum = (q.questionNumber || '').trim();
    if (!qNum) {
      throw new ExamValidationError(`Question #${i + 1} has an empty question number.`);
    }

    const qKey = qNum.toUpperCase();
    if (seenQ.has(qKey)) {
      throw new ExamValidationError(`Duplicate question number "${qNum}" found.`);
    }
    seenQ.add(qKey);

    if (isNaN(q.maxMarks) || q.maxMarks <= 0) {
      throw new ExamValidationError(`Question "${qNum}" must have positive maximum marks.`);
    }

    const co = (q.coCode || '').trim().toUpperCase();
    if (!co) {
      throw new ExamValidationError(`Question "${qNum}" must be mapped to exactly one Course Outcome.`);
    }

    if (!uniqueCOs.has(co)) {
      throw new ExamValidationError(
        `Question "${qNum}" is mapped to "${co}", which is NOT in the exam's covered CO list (${cleanCOs.join(', ')}).`
      );
    }

    mappedCOs.add(co);
  }

  // Every covered CO must have at least one mapped question
  for (const co of cleanCOs) {
    if (!mappedCOs.has(co)) {
      throw new ExamValidationError(`Covered outcome "${co}" has no questions mapped to it. Every covered CO must have at least one question.`);
    }
  }

  // Pattern checks for confirmed exam structures
  if (examType === 'INTERNAL_1' || examType === 'INTERNAL_2') {
    const totalMarks = questions.reduce((sum, q) => sum + Number(q.maxMarks), 0);
    const twoMarkCount = questions.filter((q) => Number(q.maxMarks) === 2).length;
    const tenMarkCount = questions.filter((q) => Number(q.maxMarks) === 10).length;

    if (questions.length !== 13 || totalMarks !== 50 || twoMarkCount !== 10 || tenMarkCount !== 3) {
      throw new ExamValidationError(
        `Pattern mismatch for ${examType === 'INTERNAL_1' ? 'Internal Assessment 1' : 'Internal Assessment 2'}: ` +
        `Confirmed pattern requires 13 questions (10 × 2-mark + 3 × 10-mark) totaling 50 marks. ` +
        `Current: ${questions.length} questions totaling ${totalMarks} marks.`
      );
    }
  } else if (examType === 'MODEL') {
    const totalMarks = questions.reduce((sum, q) => sum + Number(q.maxMarks), 0);
    const twoMarkCount = questions.filter((q) => Number(q.maxMarks) === 2).length;
    const eightMarkCount = questions.filter((q) => Number(q.maxMarks) === 8).length;

    if (questions.length !== 15 || totalMarks !== 60 || twoMarkCount !== 10 || eightMarkCount !== 5) {
      throw new ExamValidationError(
        'Pattern mismatch for Model Examination: Confirmed pattern requires 15 questions ' +
        '(10 × 2-mark + 5 × 8-mark) totaling 60 marks. ' +
        `Current: ${questions.length} questions totaling ${totalMarks} marks.`
      );
    }
  }
}

export async function saveExam(
  examId: number | null,
  name: string,
  examType: ExamType,
  departmentId: number,
  yearId: number,
  semesterId: number,
  sectionId: number,
  subjectId: number,
  examDate: string,
  passPercentage: number,
  coveredCOs: string[],
  questions: ExamQuestionConfig[],
  batchId?: number,
): Promise<ExamDetail> {
  const validDate = /^\d{4}-\d{2}-\d{2}$/.test(examDate) &&
    !Number.isNaN(Date.parse(`${examDate}T00:00:00Z`)) &&
    new Date(`${examDate}T00:00:00Z`).toISOString().slice(0, 10) === examDate;
  if (!examId && !validDate) {
    throw new ExamValidationError('A valid Exam Date is required.');
  }
  if (examDate && !validDate) {
    throw new ExamValidationError('Exam Date must be a valid calendar date.');
  }

  validateExamConfiguration(
    name,
    examType,
    departmentId,
    yearId,
    semesterId,
    sectionId,
    subjectId,
    passPercentage,
    coveredCOs,
    questions
  );

  const response = await fetch(apiUrl(examId ? `/api/exams/${examId}` : '/api/exams'), {
    method: examId ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: name.trim(),
      exam_date: examDate || null,
      exam_type: examType,
      batch_id: batchId,
      department_id: departmentId,
      year_id: yearId,
      semester_id: semesterId,
      section_id: sectionId,
      subject_id: subjectId,
      pass_percentage: Number(passPercentage),
      covered_cos: coveredCOs.map((c) => c.trim().toUpperCase()),
      questions: questions.map((q) => ({
        question_number: q.questionNumber.trim(),
        max_marks: Number(q.maxMarks),
        co_code: q.coCode.trim().toUpperCase(),
      })),
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ExamValidationError(data.detail || 'Failed to save exam configuration.');
  }
  return mapApiExam(data);
}
