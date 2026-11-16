import assert from 'node:assert/strict';
import { test } from 'node:test';
import { calculateLiveQuestionStatistics } from './questionStatistics';

test('live question statistics count entered zero marks and exclude blank marks', () => {
  const students = Array.from({ length: 64 }, (_, index) => ({
    id: index + 1,
    registerNo: `S${index + 1}`,
    name: `Student ${index + 1}`,
    sectionId: 1,
    batchId: 1,
  }));
  const question = {
    questionId: 1,
    questionNumber: 'Q1',
    maxMarks: 10,
    coCode: 'CO1',
  };
  const gridData: Record<string, Record<string, string>> = {};

  for (let index = 1; index <= 20; index += 1) {
    gridData[`S${index}`] = { Q1: '5' };
  }
  for (let index = 21; index <= 25; index += 1) {
    gridData[`S${index}`] = { Q1: '0' };
  }
  for (let index = 26; index <= 50; index += 1) {
    gridData[`S${index}`] = { Q1: '4' };
  }
  gridData.S51 = { Q1: '' };
  gridData.S52 = { Q1: '   ' };

  const [statistics] = calculateLiveQuestionStatistics([question], students, gridData);

  assert.equal(statistics.students_attempted, 50);
  assert.equal(statistics.students_at_least_50_percent, 20);
  assert.equal(statistics.percentage_at_least_50_percent, 40);
});

test('live question statistics use a blank percentage when no students attempted', () => {
  const statistics = calculateLiveQuestionStatistics(
    [{ questionNumber: 'Q1', maxMarks: 10, coCode: 'CO1' }],
    [{ id: 1, registerNo: 'S1', name: 'Student 1', sectionId: 1, batchId: 1 }],
    { S1: { Q1: '' } },
  );

  assert.equal(statistics[0].students_attempted, 0);
  assert.equal(statistics[0].students_at_least_50_percent, 0);
  assert.equal(statistics[0].percentage_at_least_50_percent, null);
});
