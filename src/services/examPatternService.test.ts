import assert from 'node:assert/strict';
import test from 'node:test';
import {
  AUTONOMOUS_PATTERNS,
  getAutonomousQuickStructure,
  getDefaultExamName,
  getDefaultPassPercentageForPattern,
  getExamSlotType,
  getUniversityQuickStructure,
  generateQuestionsFromGroups,
  normalizeSavedCustomExamPatterns,
} from './examPatternService';

const totalMarks = (questions: ReturnType<typeof generateQuestionsFromGroups>) =>
  questions.reduce((sum, question) => sum + question.maxMarks, 0);

const coveredQuestionCOs = (questions: ReturnType<typeof generateQuestionsFromGroups>) =>
  [...new Set(questions.map((question) => question.coCode))].sort();

const marksDistribution = (questions: ReturnType<typeof generateQuestionsFromGroups>) =>
  questions.reduce<Record<number, number>>((distribution, question) => {
    distribution[question.maxMarks] = (distribution[question.maxMarks] || 0) + 1;
    return distribution;
  }, {});

test('home-page exam slots resolve names and slot types independently', () => {
  assert.equal(getDefaultExamName('INTERNAL_1'), 'Internal Assessment 1');
  assert.equal(getDefaultExamName('INTERNAL_2'), 'Internal Assessment 2');
  assert.equal(getDefaultExamName('MODEL'), 'Model Exam');
  assert.equal(getExamSlotType('AUTONOMOUS_INTERNAL_2'), 'INTERNAL_2');
  assert.equal(getExamSlotType('AUTONOMOUS_MODEL'), 'MODEL');
});

test('University quick structures match each slot', () => {
  const internal1 = getUniversityQuickStructure('INTERNAL_1');
  const internal2 = getUniversityQuickStructure('INTERNAL_2');
  const model = getUniversityQuickStructure('MODEL');

  assert.deepEqual(internal1.coveredCOs, ['CO1', 'CO2']);
  assert.equal(internal1.questions.length, 13);
  assert.equal(totalMarks(internal1.questions), 50);
  assert.deepEqual(marksDistribution(internal1.questions), { 2: 10, 10: 3 });
  assert.deepEqual(internal2.coveredCOs, ['CO2', 'CO3']);
  assert.equal(internal2.questions.length, 13);
  assert.equal(totalMarks(internal2.questions), 50);
  assert.deepEqual(coveredQuestionCOs(internal2.questions), ['CO2', 'CO3']);
  assert.deepEqual(model.coveredCOs, ['CO1', 'CO2', 'CO3', 'CO4', 'CO5']);
  assert.equal(model.questions.length, 15);
  assert.equal(totalMarks(model.questions), 60);
  assert.deepEqual(marksDistribution(model.questions), { 2: 10, 8: 5 });
});

test('Autonomous quick structures match the originating home-page slot', () => {
  const internal1 = getAutonomousQuickStructure('INTERNAL_1');
  const internal2 = getAutonomousQuickStructure('INTERNAL_2');
  const model = getAutonomousQuickStructure('MODEL');

  assert.deepEqual(internal1.coveredCOs, ['CO1', 'CO2']);
  assert.equal(totalMarks(internal1.questions), 50);
  assert.deepEqual(marksDistribution(internal1.questions), { 2: 5, 13: 2, 14: 1 });
  assert.deepEqual(internal2.coveredCOs, ['CO2', 'CO3']);
  assert.equal(totalMarks(internal2.questions), 50);
  assert.deepEqual(coveredQuestionCOs(internal2.questions), ['CO2', 'CO3']);
  assert.deepEqual(model.coveredCOs, ['CO1', 'CO2', 'CO3', 'CO4', 'CO5']);
  assert.equal(totalMarks(model.questions), 100);
  assert.deepEqual(marksDistribution(model.questions), { 2: 10, 13: 5, 15: 1 });
});

test('pattern defaults keep University at 50 and Autonomous at 40', () => {
  assert.equal(getDefaultPassPercentageForPattern('UNIVERSITY'), 50);
  assert.equal(getDefaultPassPercentageForPattern('AUTONOMOUS'), 40);
  assert.equal(getDefaultPassPercentageForPattern('CUSTOM'), 50);
});

test('Autonomous Internal 1 generates 8 questions, 50 marks, and CO1/CO2 coverage', () => {
  const questions = generateQuestionsFromGroups(AUTONOMOUS_PATTERNS.INTERNAL_1, ['CO1', 'CO2']);
  assert.equal(questions.length, 8);
  assert.equal(totalMarks(questions), 50);
  assert.deepEqual(coveredQuestionCOs(questions), ['CO1', 'CO2']);
  assert.deepEqual(questions.map((question) => question.questionNumber), Array.from({ length: 8 }, (_, index) => `Q${index + 1}`));
});

test('Autonomous Internal 2 generates 8 questions, 50 marks, and CO2/CO3 coverage', () => {
  const questions = generateQuestionsFromGroups(AUTONOMOUS_PATTERNS.INTERNAL_2, ['CO2', 'CO3']);
  assert.equal(questions.length, 8);
  assert.equal(totalMarks(questions), 50);
  assert.deepEqual(coveredQuestionCOs(questions), ['CO2', 'CO3']);
});

test('Autonomous Model generates 16 questions, 100 marks, and all five COs', () => {
  const questions = generateQuestionsFromGroups(AUTONOMOUS_PATTERNS.MODEL, ['CO1', 'CO2', 'CO3', 'CO4', 'CO5']);
  assert.equal(questions.length, 16);
  assert.equal(totalMarks(questions), 100);
  assert.deepEqual(coveredQuestionCOs(questions), ['CO1', 'CO2', 'CO3', 'CO4', 'CO5']);
});

test('group generation preserves existing CO choices in question order', () => {
  const questions = generateQuestionsFromGroups(
    [{ quantity: 2, marksPerQuestion: 5 }],
    ['CO1', 'CO2'],
    [
      { questionNumber: 'Q1', maxMarks: 2, coCode: 'CO2' },
      { questionNumber: 'Q2', maxMarks: 2, coCode: 'CO1' },
    ]
  );
  assert.deepEqual(questions.map((question) => question.coCode), ['CO2', 'CO1']);
});

test('saved pattern API groups normalize for loading after refresh', () => {
  assert.deepEqual(
    normalizeSavedCustomExamPatterns([{
      id: 7,
      name: 'Autonomous Internal Special',
      groups: [
        { quantity: 5, marks_per_question: 2 },
        { quantity: 2, marks_per_question: 13 },
        { quantity: 1, marks_per_question: 14 },
      ],
    }]),
    [{
      id: 7,
      name: 'Autonomous Internal Special',
      groups: [
        { quantity: 5, marksPerQuestion: 2 },
        { quantity: 2, marksPerQuestion: 13 },
        { quantity: 1, marksPerQuestion: 14 },
      ],
    }]
  );
});
