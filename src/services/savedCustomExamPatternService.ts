import { apiUrl } from '../config';
import {
  ExamPatternGroup,
  normalizeSavedCustomExamPatterns,
  SavedCustomExamPattern,
} from './examPatternService';

export async function loadSavedCustomExamPatterns(): Promise<SavedCustomExamPattern[]> {
  const response = await fetch(apiUrl('/api/custom-exam-patterns'));
  if (!response.ok) throw new Error('Unable to load saved custom patterns.');
  const data = await response.json();
  return normalizeSavedCustomExamPatterns(data);
}

export async function saveCustomExamPattern(
  name: string,
  groups: ExamPatternGroup[]
): Promise<SavedCustomExamPattern> {
  const response = await fetch(apiUrl('/api/custom-exam-patterns'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, groups: groups.map((group) => ({
      quantity: group.quantity,
      marks_per_question: group.marksPerQuestion,
    })) }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Unable to save custom pattern.');
  return {
    id: Number(data.id),
    name: data.name,
    groups: data.groups.map((group: any) => ({
      quantity: Number(group.quantity),
      marksPerQuestion: Number(group.marks_per_question ?? group.marksPerQuestion),
    })),
  };
}

export async function deleteSavedCustomExamPattern(patternId: number): Promise<void> {
  const response = await fetch(apiUrl(`/api/custom-exam-patterns/${patternId}`), { method: 'DELETE' });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || 'Unable to delete saved custom pattern.');
  }
}