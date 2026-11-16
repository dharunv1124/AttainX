import type { ExamQuestionConfig } from '../types';

export interface ExamPatternGroup {
  quantity: number;
  marksPerQuestion: number;
}

export interface SavedCustomExamPattern {
  id: number;
  name: string;
  groups: ExamPatternGroup[];
}

export function normalizeSavedCustomExamPatterns(data: unknown): SavedCustomExamPattern[] {
  if (!Array.isArray(data)) return [];
  return data.map((pattern: any) => ({
    id: Number(pattern.id),
    name: pattern.name,
    groups: (pattern.groups || []).map((group: any) => ({
      quantity: Number(group.quantity),
      marksPerQuestion: Number(group.marks_per_question ?? group.marksPerQuestion),
    })),
  }));
}

export type PatternFamily = 'UNIVERSITY' | 'AUTONOMOUS' | 'CUSTOM';

export function getDefaultPassPercentageForPattern(family: PatternFamily): number {
  return family === 'AUTONOMOUS' ? 40 : 50;
}

export const AUTONOMOUS_PATTERNS: Record<string, ExamPatternGroup[]> = {
  INTERNAL_1: [
    { quantity: 5, marksPerQuestion: 2 },
    { quantity: 2, marksPerQuestion: 13 },
    { quantity: 1, marksPerQuestion: 14 },
  ],
  INTERNAL_2: [
    { quantity: 5, marksPerQuestion: 2 },
    { quantity: 2, marksPerQuestion: 13 },
    { quantity: 1, marksPerQuestion: 14 },
  ],
  MODEL: [
    { quantity: 10, marksPerQuestion: 2 },
    { quantity: 5, marksPerQuestion: 13 },
    { quantity: 1, marksPerQuestion: 15 },
  ],
};

export type ExamSlotType = 'INTERNAL_1' | 'INTERNAL_2' | 'MODEL';

export function getExamSlotType(examType: string): ExamSlotType {
  if (examType.endsWith('INTERNAL_2')) return 'INTERNAL_2';
  if (examType.endsWith('MODEL')) return 'MODEL';
  return 'INTERNAL_1';
}

export function getDefaultExamName(examType: string): string {
  const slotType = getExamSlotType(examType);
  if (slotType === 'INTERNAL_2') return 'Internal Assessment 2';
  if (slotType === 'MODEL') return 'Model Exam';
  return 'Internal Assessment 1';
}

export interface ExamQuickStructure {
  coveredCOs: string[];
  questions: ExamQuestionConfig[];
}

export function getUniversityQuickStructure(slotType: ExamSlotType): ExamQuickStructure {
  const coveredCOs = slotType === 'INTERNAL_2'
    ? ['CO2', 'CO3']
    : slotType === 'MODEL'
      ? ['CO1', 'CO2', 'CO3', 'CO4', 'CO5']
      : ['CO1', 'CO2'];
  const [defaultCO, altCO] = coveredCOs;
  const questions: ExamQuestionConfig[] = [];

  if (slotType === 'MODEL') {
    for (let index = 0; index < 10; index += 1) {
      questions.push({
        questionNumber: `Q${index + 1}`,
        maxMarks: 2,
        coCode: coveredCOs[index % coveredCOs.length],
      });
    }
    for (let index = 0; index < 5; index += 1) {
      questions.push({
        questionNumber: `Q${index + 11}`,
        maxMarks: 8,
        coCode: coveredCOs[index % coveredCOs.length],
      });
    }
  } else {
    for (let index = 1; index <= 10; index += 1) {
      questions.push({
        questionNumber: `Q${index}`,
        maxMarks: 2,
        coCode: index <= 5 ? defaultCO : altCO,
      });
    }
    questions.push({ questionNumber: 'Q11', maxMarks: 10, coCode: defaultCO });
    questions.push({ questionNumber: 'Q12', maxMarks: 10, coCode: altCO });
    questions.push({ questionNumber: 'Q13', maxMarks: 10, coCode: defaultCO });
  }

  return { coveredCOs, questions };
}

export function getAutonomousQuickStructure(slotType: ExamSlotType): ExamQuickStructure {
  const coveredCOs = slotType === 'INTERNAL_2'
    ? ['CO2', 'CO3']
    : slotType === 'MODEL'
      ? ['CO1', 'CO2', 'CO3', 'CO4', 'CO5']
      : ['CO1', 'CO2'];
  return {
    coveredCOs,
    questions: generateQuestionsFromGroups(AUTONOMOUS_PATTERNS[slotType], coveredCOs),
  };
}

export function generateQuestionsFromGroups(
  groups: ExamPatternGroup[],
  coveredCOs: string[],
  existingQuestions: ExamQuestionConfig[] = []
): ExamQuestionConfig[] {
  if (!groups.length || groups.some((group) =>
    !Number.isSafeInteger(group.quantity) || group.quantity <= 0 ||
    !Number.isFinite(group.marksPerQuestion) || group.marksPerQuestion <= 0
  )) {
    throw new Error('Each group needs a positive whole-number question count and positive marks per question.');
  }

  const validCOs = coveredCOs.map((co) => co.trim().toUpperCase()).filter(Boolean);
  if (!validCOs.length) throw new Error('At least one covered CO is required to generate questions.');

  const questions: ExamQuestionConfig[] = [];
  const seenQuestionNumbers = new Set<string>();
  for (const group of groups) {
    for (let offset = 0; offset < group.quantity; offset += 1) {
      const questionNumber = `Q${questions.length + 1}`;
      if (seenQuestionNumbers.has(questionNumber.toUpperCase())) {
        throw new Error('The generated pattern contains duplicate question numbers.');
      }
      seenQuestionNumbers.add(questionNumber.toUpperCase());
      const existingCO = existingQuestions[questions.length]?.coCode.trim().toUpperCase();
      questions.push({
        questionNumber,
        maxMarks: group.marksPerQuestion,
        coCode: existingCO && validCOs.includes(existingCO)
          ? existingCO
          : validCOs[questions.length % validCOs.length],
      });
    }
  }
  return questions;
}
