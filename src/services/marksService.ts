import { ExamDetail, Student, StudentMarkRecord, CanonicalExamResult, ExamCOStatistics } from '../types';
import { apiUrl } from '../config';

const MARKS_STORAGE_PREFIX = 'obe_marks_exam_';
const RESULTS_STORAGE_PREFIX = 'obe_results_exam_';

export class MarksValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'MarksValidationError';
  }
}

export async function loadExamQuestions(examId: number): Promise<ExamDetail['questions']> {
  const response = await fetch(apiUrl(`/api/exams/${examId}/questions`));
  if (!response.ok) {
    throw new Error(`Failed to load configured exam questions (${response.status})`);
  }
  const data = await response.json();
  return (Array.isArray(data) ? data : []).map((question: any) => ({
    questionId: Number(question.id),
    questionNumber: question.question_number || question.questionNumber,
    maxMarks: Number(question.max_marks ?? question.maxMarks),
    coCode: question.co_code || question.coCode,
  }));
}

/**
 * 1. Load the students belonging to the exam's selected Department -> Year -> Semester -> Section.
 */
export async function loadExamRoster(exam: ExamDetail): Promise<Student[]> {
  const res = await fetch(apiUrl(`/api/exams/${exam.id}/roster`));
  if (!res.ok) {
    throw new Error(`Failed to load exam roster (${res.status})`);
  }
  const data = await res.json();
  const list = Array.isArray(data) ? data : (Array.isArray(data.students) ? data.students : []);
  return list.map((s: any) => ({
    id: s.id,
    name: s.name,
    registerNo: s.register_no || s.registerNo,
    sectionId: s.section_id || s.sectionId,
  }));
}

/**
 * Loads saved marks and calculated CO results for an exam.
 */
export async function loadExamMarksAndResults(
  examId: number
): Promise<{ marks: StudentMarkRecord[]; calculationResult: CanonicalExamResult | null; questionCoStatistics: ExamCOStatistics | null }> {
  let marks: StudentMarkRecord[] = [];
  let calculationResult: CanonicalExamResult | null = null;
  let questionCoStatistics: ExamCOStatistics | null = null;

  try {
    const res = await fetch(apiUrl(`/api/exams/${examId}/marks`));
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data.marks)) {
        marks = data.marks.map((m: any) => ({
          registerNo: m.register_no || m.registerNo,
          questionId: m.question_id ?? m.questionId,
          questionNumber: m.question_number || m.questionNumber,
          obtainedMark: Number(m.obtained_mark ?? m.obtainedMark),
        }));
      }
      if (data.calculation_result || data.calculationResult) {
        calculationResult = data.calculation_result || data.calculationResult;
      }
      questionCoStatistics = data.question_co_statistics || data.questionCoStatistics || null;
    }
  } catch {
    // Network fallback
  }

  // Check localStorage if API had empty results
  if (marks.length === 0) {
    try {
      const storedMarks = localStorage.getItem(`${MARKS_STORAGE_PREFIX}${examId}`);
      if (storedMarks) {
        marks = JSON.parse(storedMarks);
      }
    } catch {
      // Ignore
    }
  }

  if (!calculationResult) {
    try {
      const storedRes = localStorage.getItem(`${RESULTS_STORAGE_PREFIX}${examId}`);
      if (storedRes) {
        calculationResult = JSON.parse(storedRes);
      }
    } catch {
      // Ignore
    }
  }

  return { marks, calculationResult, questionCoStatistics };
}

/**
 * Validates entered marks and saves them to the backend.
 * The backend recalculates the CO results using the Phase 3 authoritative calculation engine.
 */
export async function saveExamMarks(
  exam: ExamDetail,
  enrolledStudents: Student[],
  marks: StudentMarkRecord[],
  requireComplete: boolean = false
): Promise<{ marks: StudentMarkRecord[]; calculationResult: CanonicalExamResult; questionCoStatistics: ExamCOStatistics | null }> {
  // 1. DATA CONSISTENCY CHECK
  // Verify that every student belongs to the exam's configured class/section
  const allowedRegs = new Set(enrolledStudents.map((s) => s.registerNo.trim().toUpperCase()));
  for (const m of marks) {
    const reg = m.registerNo.trim().toUpperCase();
    if (!allowedRegs.has(reg)) {
      throw new MarksValidationError(
        `Student '${reg}' does not belong to the exam's configured class/section (Section ${exam.sectionName}). ` +
        'Marks for students outside the exam cohort are strictly rejected.'
      );
    }
  }

  // 2. MARK VALIDATION
  // Numeric, non-negative, <= question maximum
  const qMap = new Map<string, number>();
  for (const q of exam.questions) {
    qMap.set(q.questionNumber.trim().toUpperCase(), Number(q.maxMarks));
  }

  const cleanMarks: StudentMarkRecord[] = [];

  for (const m of marks) {
    const reg = m.registerNo.trim().toUpperCase();
    const qNum = m.questionNumber.trim().toUpperCase();
    const configuredQuestion = exam.questions.find(
      (q) => q.questionNumber.trim().toUpperCase() === qNum
    );

    if (!qMap.has(qNum)) {
      throw new MarksValidationError(`Question "${qNum}" is not configured for this exam.`);
    }

    const val = Number(m.obtainedMark);
    if (isNaN(val)) {
      throw new MarksValidationError(
        `Mark for student "${reg}" on question "${qNum}" must be a valid number.`
      );
    }

    if (val < 0) {
      throw new MarksValidationError(
        `Mark cannot be negative: got ${val} for student "${reg}" on question "${qNum}". Negative marks are strictly rejected.`
      );
    }

    const maxAllowed = qMap.get(qNum)!;
    if (val > maxAllowed) {
      throw new MarksValidationError(
        `Obtained mark ${val} exceeds question "${qNum}" maximum marks ${maxAllowed} for student "${reg}". ` +
        'Values exceeding maximum marks are strictly rejected without silent clamping.'
      );
    }

    cleanMarks.push({
      registerNo: reg,
        questionId: configuredQuestion?.questionId,
      questionNumber: qNum,
      obtainedMark: val,
    });
  }

  // 3. SEND TO FASTAPI BACKEND FOR PERSISTENCE & AUTHORITATIVE RECALCULATION
  const response = await fetch(apiUrl(`/api/exams/${exam.id}/marks?require_complete=${requireComplete}`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      marks: cleanMarks.map((m) => ({
        register_no: m.registerNo,
        ...(m.questionId !== undefined ? { question_id: m.questionId } : {}),
        question_number: m.questionNumber,
        obtained_mark: m.obtainedMark,
      })),
    }),
  });

  const data = await response.json();

  if (!response.ok) {
    throw new MarksValidationError(data.detail || data.error || 'Failed to save marks and calculate CO results.');
  }

  const calcResult = data.calculation_result || data.calculationResult;

  // Persist locally for instant reload persistence
  localStorage.setItem(`${MARKS_STORAGE_PREFIX}${exam.id}`, JSON.stringify(cleanMarks));
  if (calcResult) {
    localStorage.setItem(`${RESULTS_STORAGE_PREFIX}${exam.id}`, JSON.stringify(calcResult));
  }

  return {
    marks: cleanMarks,
    calculationResult: calcResult,
    questionCoStatistics: data.question_co_statistics || data.questionCoStatistics || null,
  };
}

/**
 * Downloads the authoritative Excel (.xlsx) report for an exam from the FastAPI backend.
 */
async function downloadExamReport(examId: number, format: 'excel' | 'pdf'): Promise<void> {
  const extension = format === 'excel' ? 'xlsx' : 'pdf';
  const res = await fetch(apiUrl(`/api/exams/${examId}/report/${format}`));
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `Failed to generate ${format.toUpperCase()} report (${res.status})`);
  }
  const blob = await res.blob();
  if (blob.size === 0) {
    throw new Error(`The ${format.toUpperCase()} report was empty and could not be downloaded.`);
  }
  const disposition = res.headers.get('Content-Disposition') || '';
  let filename = `Exam_${examId}_CO_Attainment.${extension}`;
  const match = disposition.match(/filename="?([^";]+)"?/);
  if (match && match[1]) {
    filename = match[1];
  }
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
}

export async function downloadExamExcelReport(examId: number): Promise<void> {
  return downloadExamReport(examId, 'excel');
}

/**
 * Downloads the clean, printable PDF (.pdf) report for an exam from the FastAPI backend.
 */
export async function downloadExamPdfReport(examId: number): Promise<void> {
  return downloadExamReport(examId, 'pdf');
}

