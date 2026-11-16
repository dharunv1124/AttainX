import type { ExamCOStatistics, ExamQuestionConfig, Student } from '../types';

export function calculateLiveQuestionStatistics(
  questions: ExamQuestionConfig[],
  students: Student[],
  gridData: Record<string, Record<string, string>>,
): ExamCOStatistics['questions'] {
  return questions.map((question) => {
    let studentsAttempted = 0;
    let studentsAtLeastHalf = 0;

    for (const student of students) {
      const rawMark = gridData[student.registerNo]?.[question.questionNumber];
      if (rawMark === undefined || rawMark === null || rawMark.trim() === '') {
        continue;
      }

      const mark = Number(rawMark);
      if (!Number.isFinite(mark)) {
        continue;
      }

      studentsAttempted += 1;
      if (mark >= question.maxMarks / 2) {
        studentsAtLeastHalf += 1;
      }
    }

    return {
      question_number: question.questionNumber,
      co_code: question.coCode,
      students_at_least_50_percent: studentsAtLeastHalf,
      students_attempted: studentsAttempted,
      percentage_at_least_50_percent: studentsAttempted
        ? (studentsAtLeastHalf / studentsAttempted) * 100
        : null,
    };
  });
}
