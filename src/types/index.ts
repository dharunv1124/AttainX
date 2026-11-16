export type UserRole = 'ADMIN' | 'FACULTY' | 'CLASS_ADVISOR' | 'HOD';

export interface User {
  username: string;
  fullName: string;
  email: string;
  role: UserRole;
}

export interface AuthSession {
  token: string;
  username: string;
  fullName: string;
  role: UserRole;
}

export interface Department {
  id: number;
  name: string;
  code: string;
}

export interface Batch {
  id: number;
  batchName: string;
  startYear: number;
  endYear: number;
  isActive: boolean;
  isDefault: boolean;
}

export interface Year {
  id: number;
  yearNumber: number;
  name: string;
}

export interface Semester {
  id: number;
  semesterNumber: number;
  name: string;
  yearId: number;
}

export interface Section {
  id: number;
  name: string;
  batchId: number;
  departmentId: number;
  departmentCode?: string;
  yearId: number;
  yearName?: string;
}

export interface Subject {
  id: number;
  name: string;
  batchId: number;
  isActive: boolean;
}

export interface Student {
  id: number;
  registerNo: string;
  name: string;
  sectionId: number;
  batchId: number;
  archivedAt?: string | null;
}

export interface StudentImportPreview {
  section_id: number;
  batch_id: number;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  new_students: number;
  already_assigned: number;
  eligible_for_restoration: number;
  placement_conflicts: number;
  duplicate_register_numbers: string[];
  identity_resolutions: StudentImportIdentityResolution[];
  errors: string[];
}

export interface StudentImportIdentityResolution {
  row_number: number;
  register_no: string;
  uploaded_name: string;
  selected_student_id: number | null;
  selected_student_name: string | null;
  candidate_student_ids: number[];
  other_student_ids: number[];
  resolution_status: string;
  destination_section_id: number;
  destination_section_name: string;
}

export interface StudentImportResult {
  section_id: number;
  batch_id: number;
  imported_count: number;
  restored_count: number;
  already_assigned_count: number;
  placed_count: number;
  skipped_conflict_count: number;
  message: string;
}

export type ExamType =
  | 'INTERNAL_1'
  | 'INTERNAL_2'
  | 'MODEL'
  | 'CUSTOM'
  | 'AUTONOMOUS_INTERNAL_1'
  | 'AUTONOMOUS_INTERNAL_2'
  | 'AUTONOMOUS_MODEL';

export interface ExamQuestionConfig {
  questionId?: number;
  questionNumber: string;
  maxMarks: number;
  coCode: string;
}

export interface Exam {
  id: number;
  name: string;
  examDate: string | null;
  examType: ExamType;
  batchId: number;
  departmentId: number;
  yearId: number;
  semesterId: number;
  sectionId: number;
  subjectId: number;
  passPercentage: number;
  coveredCOs: string[];
  questions: ExamQuestionConfig[];
  createdAt: string;
  updatedAt: string;
}

export interface ExamDetail extends Exam {
  departmentName: string;
  departmentCode: string;
  yearName: string;
  semesterName: string;
  sectionName: string;
  subjectName: string;
  totalMarks: number;
  totalQuestions: number;
  studentCount: number;
}

export interface StudentMarkRecord {
  registerNo: string;
  questionId?: number;
  questionNumber: string;
  obtainedMark: number;
}

export interface StudentCOResult {
  coCode?: string;
  co_code?: string;
  coMaxMarks?: number;
  co_max_marks?: number;
  obtainedMarks?: number;
  obtained_marks?: number;
  coPercentage?: number;
  co_percentage?: number;
  attainment: 1 | 0; // Strictly 1 or 0
}

export interface StudentExamResult {
  registerNo?: string;
  register_no?: string;
  name: string;
  questionMarks?: Record<string, number>;
  question_marks?: Record<string, number>;
  totalObtained?: number;
  total_obtained?: number;
  coResults?: Record<string, StudentCOResult>;
  co_results?: Record<string, StudentCOResult>;
}

export interface CanonicalExamResult {
  examId?: number | string;
  exam_id?: number | string;
  passPercentage?: number;
  pass_percentage?: number;
  coveredCOs?: string[];
  covered_cos?: string[];
  coMaxMarks?: Record<string, number>;
  co_max_marks?: Record<string, number>;
  students: StudentExamResult[];
  overallCOAttainment?: Record<string, OverallCOAttainment>;
  overall_co_attainment?: Record<string, OverallCOAttainment>;
}

export interface ExamCOStatistics {
  questions: Array<{
    question_number: string;
    co_code: string;
    students_at_least_50_percent: number;
    students_attempted: number;
    percentage_at_least_50_percent: number | null;
  }>;
  co_averages: Array<{
    co_code: string;
    average_percentage: number | null;
  }>;
}

export interface OverallCOAttainment {
  coCode?: string;
  co_code?: string;
  totalStudents?: number;
  total_students?: number;
  studentsAttainingCO?: number;
  students_attaining_co?: number;
  attainmentPercentage?: number;
  attainment_percentage?: number;
  attainmentLevel?: number | null;
  attainment_level?: number | null;
}
