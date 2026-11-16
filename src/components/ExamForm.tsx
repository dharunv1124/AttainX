import React, { useState, useEffect } from 'react';
import { ExamDetail, ExamQuestionConfig, ExamType } from '../types';
import { saveExam, ExamValidationError } from '../services/examService';
import { apiUrl } from '../config';
import {
  AUTONOMOUS_PATTERNS,
  ExamPatternGroup,
  ExamSlotType,
  getAutonomousQuickStructure,
  getDefaultExamName,
  getDefaultPassPercentageForPattern,
  getExamSlotType,
  getUniversityQuickStructure,
  generateQuestionsFromGroups,
  PatternFamily,
  SavedCustomExamPattern,
} from '../services/examPatternService';
import {
  deleteSavedCustomExamPattern,
  loadSavedCustomExamPatterns,
  saveCustomExamPattern,
} from '../services/savedCustomExamPatternService';

interface ExamFormProps {
  initialExam?: ExamDetail | null;
  initialName?: string;
  initialType?: ExamType;
  batchId: number;
  departmentId: number;
  yearId: number;
  semesterId: number;
  sectionId: number;
  subjectId: number;
  onSaveSuccess: (savedExam: ExamDetail) => void;
  onCancel: () => void;
}

const ALL_COS = ['CO1', 'CO2', 'CO3', 'CO4', 'CO5'];

interface PatternGroup {
  quantity: string;
  marksPerQuestion: string;
}

const groupsFromQuestions = (questions: ExamQuestionConfig[]): PatternGroup[] => {
  const groups: PatternGroup[] = [];
  questions.forEach((question) => {
    const marks = String(question.maxMarks);
    const lastGroup = groups[groups.length - 1];
    if (lastGroup && lastGroup.marksPerQuestion === marks) {
      lastGroup.quantity = String(Number(lastGroup.quantity) + 1);
    } else {
      groups.push({ quantity: '1', marksPerQuestion: marks });
    }
  });
  return groups.length ? groups : [{ quantity: '1', marksPerQuestion: '2' }];
};

export const ExamForm: React.FC<ExamFormProps> = ({
  initialExam,
  initialName,
  initialType,
  batchId,
  departmentId,
  yearId,
  semesterId,
  sectionId,
  subjectId,
  onSaveSuccess,
  onCancel,
}) => {
  const sourceType = initialExam?.examType || initialType || 'INTERNAL_1';
  const slotType = getExamSlotType(sourceType);
  const initialPatternFamily: PatternFamily = sourceType.startsWith('AUTONOMOUS')
    ? 'AUTONOMOUS'
    : sourceType === 'CUSTOM'
      ? 'CUSTOM'
      : 'UNIVERSITY';
  const defaultStructure = initialPatternFamily === 'AUTONOMOUS'
    ? getAutonomousQuickStructure(slotType)
    : getUniversityQuickStructure(slotType);
  const [name, setName] = useState(initialExam?.name || initialName || getDefaultExamName(sourceType));
  const [examDate, setExamDate] = useState(initialExam?.examDate || '');
  const [examType, setExamType] = useState<ExamType>(sourceType);
  const [patternFamily, setPatternFamily] = useState<PatternFamily>(initialPatternFamily);
  const [passPercentage, setPassPercentage] = useState<number>(initialExam?.passPercentage || 50.0);
  const [coveredCOs, setCoveredCOs] = useState<string[]>(
    initialExam?.coveredCOs || defaultStructure.coveredCOs
  );
  const [questions, setQuestions] = useState<ExamQuestionConfig[]>(
    initialExam?.questions || defaultStructure.questions
  );
  const [error, setError] = useState<string | null>(null);
  const [patternGroups, setPatternGroups] = useState<PatternGroup[]>(() =>
    groupsFromQuestions(initialExam?.questions || questions)
  );
  const [savedMarksStatus, setSavedMarksStatus] = useState<'checking' | 'saved' | 'none'>(
    initialExam ? 'checking' : 'none'
  );
  const [savedPatterns, setSavedPatterns] = useState<SavedCustomExamPattern[]>([]);
  const [patternName, setPatternName] = useState('');

  useEffect(() => {
    if (!initialExam) {
      setSavedMarksStatus('none');
      return;
    }

    let active = true;
    const checkSavedMarks = async () => {
      try {
        const response = await fetch(apiUrl(`/api/exams/${initialExam.id}/marks`));
        if (!response.ok) throw new Error('Unable to verify saved marks.');
        const data = await response.json();
        let hasLocalMarks = false;
        try {
          const localMarks = localStorage.getItem(`obe_marks_exam_${initialExam.id}`);
          hasLocalMarks = Boolean(localMarks && JSON.parse(localMarks).length > 0);
        } catch {
          hasLocalMarks = true;
        }
        if (active) {
          setSavedMarksStatus(data.marks?.length > 0 || hasLocalMarks ? 'saved' : 'none');
        }
      } catch {
        if (active) setSavedMarksStatus('saved');
      }
    };

    void checkSavedMarks();
    return () => {
      active = false;
    };
  }, [initialExam?.id]);

  useEffect(() => {
    let active = true;
    loadSavedCustomExamPatterns()
      .then((patterns) => {
        if (active) setSavedPatterns(patterns);
      })
      .catch((loadError: unknown) => {
        if (active) setError(loadError instanceof Error ? loadError.message : 'Unable to load saved patterns.');
      });
    return () => {
      active = false;
    };
  }, []);

  const parsedPatternGroups = patternGroups.map((group) => ({
    quantity: Number(group.quantity),
    marksPerQuestion: Number(group.marksPerQuestion),
  }));
  const patternQuestions = parsedPatternGroups.reduce(
    (sum, group) => sum + (Number.isSafeInteger(group.quantity) && group.quantity > 0 ? group.quantity : 0),
    0
  );
  const patternTotalMarks = parsedPatternGroups.reduce(
    (sum, group) => sum + (
      Number.isSafeInteger(group.quantity) && group.quantity > 0 &&
      Number.isFinite(group.marksPerQuestion) && group.marksPerQuestion > 0
        ? group.quantity * group.marksPerQuestion
        : 0
    ),
    0
  );
  const patternIsValid = patternGroups.length > 0 && parsedPatternGroups.every(
    (group) => Number.isSafeInteger(group.quantity) && group.quantity > 0 &&
      Number.isFinite(group.marksPerQuestion) && group.marksPerQuestion > 0
  ) && Number.isSafeInteger(patternQuestions) && Number.isFinite(patternTotalMarks);

  // Toggle covered CO selection (Faculty authoritative, never inferred)
  const toggleCO = (co: string) => {
    let nextCOs: string[];
    if (coveredCOs.includes(co)) {
      nextCOs = coveredCOs.filter((c) => c !== co);
    } else {
      nextCOs = [...coveredCOs, co].sort();
    }
    setCoveredCOs(nextCOs);

    // If an existing question was mapped to a deselected CO, reassign it to an available covered CO
    if (nextCOs.length > 0) {
      setQuestions((prev) =>
        prev.map((q) => (q.coCode === co ? { ...q, coCode: nextCOs[0] } : q))
      );
    }
  };

  // Helper to pre-populate question structure from confirmed patterns
  const applyConfirmedPattern = (type: ExamSlotType) => {
    const structure = getUniversityQuickStructure(type);
    setCoveredCOs(structure.coveredCOs);
    setQuestions(structure.questions);
    setExamType(type);
    setPatternFamily('UNIVERSITY');
    setPassPercentage(getDefaultPassPercentageForPattern('UNIVERSITY'));
  };

  const applyAutonomousPattern = (key: ExamSlotType) => {
    const structure = getAutonomousQuickStructure(key);
    const autonomousType = `AUTONOMOUS_${key}` as ExamType;

    setPatternFamily('AUTONOMOUS');
    setExamType(autonomousType);
    setPassPercentage(getDefaultPassPercentageForPattern('AUTONOMOUS'));
    setCoveredCOs(structure.coveredCOs);
    setPatternGroups(AUTONOMOUS_PATTERNS[key].map((group) => ({
      quantity: String(group.quantity),
      marksPerQuestion: String(group.marksPerQuestion),
    })));
    setQuestions(structure.questions);
  };

  const handleAddQuestion = () => {
    const nextNum = `Q${questions.length + 1}`;
    const defaultCO = coveredCOs.length > 0 ? coveredCOs[0] : 'CO1';
    setQuestions([...questions, { questionNumber: nextNum, maxMarks: 2, coCode: defaultCO }]);
  };

  const handleRemoveQuestion = (index: number) => {
    setQuestions(questions.filter((_, idx) => idx !== index));
  };

  const handleQuestionChange = (index: number, field: keyof ExamQuestionConfig, val: any) => {
    const updated = [...questions];
    updated[index] = { ...updated[index], [field]: val };
    setQuestions(updated);
  };

  const generateCustomPattern = () => {
    if (!patternIsValid) {
      setError('Each group needs a positive whole-number question count and positive marks per question.');
      return;
    }

    if (patternFamily === 'CUSTOM' && initialExam?.questions.length &&
      !window.confirm('Replace the existing custom question pattern? CO mappings will be retained by question order.')) {
      return;
    }

    try {
      setQuestions(generateQuestionsFromGroups(parsedPatternGroups, coveredCOs, questions));
      setError(null);
    } catch (generationError) {
      setError(generationError instanceof Error ? generationError.message : 'Unable to generate questions.');
    }
  };

  const handleSavePattern = async () => {
    if (!patternName.trim() || !patternIsValid) return;
    try {
      const savedPattern = await saveCustomExamPattern(patternName.trim(), parsedPatternGroups);
      setSavedPatterns((current) => [...current, savedPattern].sort((a, b) => a.name.localeCompare(b.name)));
      setPatternName('');
      setError(null);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Unable to save custom pattern.');
    }
  };

  const handleLoadPattern = (pattern: SavedCustomExamPattern) => {
    setPatternGroups(pattern.groups.map((group) => ({
      quantity: String(group.quantity),
      marksPerQuestion: String(group.marksPerQuestion),
    })));
    setPatternName(pattern.name);
    setPatternFamily('CUSTOM');
    setExamType('CUSTOM');
  };

  const handleDeletePattern = async (pattern: SavedCustomExamPattern) => {
    if (!window.confirm(`Delete saved pattern "${pattern.name}"? Existing exams will not be changed.`)) return;
    try {
      await deleteSavedCustomExamPattern(pattern.id);
      setSavedPatterns((current) => current.filter((item) => item.id !== pattern.id));
      setError(null);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : 'Unable to delete saved pattern.');
    }
  };

  const totalMarks = questions.reduce((acc, q) => acc + (Number(q.maxMarks) || 0), 0);

  // Mapped COs check
  const mappedCOs = new Set(questions.map((q) => q.coCode));
  const unmappedCoveredCOs = coveredCOs.filter((co) => !mappedCOs.has(co));

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (savedMarksStatus !== 'none') {
      setError('This exam has saved marks, or their status could not be verified. Its configuration cannot be changed.');
      return;
    }

    try {
      const saved = await saveExam(
        initialExam?.id || null,
        name,
        examType,
        departmentId,
        yearId,
        semesterId,
        sectionId,
        subjectId,
        examDate,
        passPercentage,
        coveredCOs,
        questions,
        batchId
      );
      onSaveSuccess(saved);
    } catch (err: any) {
      setError(err.message || 'Failed to save exam configuration.');
    }
  };

  return (
    <form onSubmit={handleSave} className="bg-white rounded-lg border border-slate-200 p-5 shadow-2xs space-y-5">
      <div className="flex items-center justify-between border-b border-slate-200 pb-3">
        <div>
          <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
            {initialExam ? 'Edit Exam Configuration' : 'EXAM CONFIGURATION'}
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Define exam type, covered COs, pass threshold, and question-to-CO mappings
          </p>
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="cursor-pointer bg-white border border-slate-300 hover:border-slate-400 text-slate-700 text-xs font-medium px-3 py-1.5 rounded transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={savedMarksStatus !== 'none'}
            className="cursor-pointer bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold px-4 py-1.5 rounded shadow-2xs transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Validate & Save Configuration
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 text-xs rounded p-3">
          <span className="font-bold">Validation Error: </span> {error}
        </div>
      )}

      {savedMarksStatus === 'saved' && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 text-xs rounded p-3">
          This exam has saved marks, or its marks could not be verified. Configuration changes are disabled to protect them.
        </div>
      )}

      <fieldset disabled={savedMarksStatus !== 'none'} className="min-w-0 border-0 p-0 m-0 space-y-5 disabled:opacity-60">
      {/* Step 4: Exam Details & Pattern */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 bg-slate-50 border border-slate-200 rounded-md p-4">
        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">Exam Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full text-xs bg-white border border-slate-300 rounded px-3 py-1.5 text-slate-900 focus:outline-blue-500"
            placeholder="e.g. Internal Assessment 1"
            required
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1" htmlFor="exam-date">
            Exam Date
          </label>
          <input
            id="exam-date"
            type="date"
            value={examDate}
            onChange={(event) => setExamDate(event.target.value)}
            className="w-full text-xs bg-white border border-slate-300 rounded px-3 py-1.5 text-slate-900 focus:outline-blue-500"
            required={!initialExam}
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">
            Exam Pattern / Type
          </label>
          <select
            value={patternFamily}
            onChange={(e) => {
              const nextFamily = e.target.value as PatternFamily;
              if (nextFamily === 'AUTONOMOUS') {
                setPatternFamily(nextFamily);
                setExamType(`AUTONOMOUS_${slotType}` as ExamType);
                setPassPercentage(getDefaultPassPercentageForPattern(nextFamily));
                if (!initialExam) {
                  applyAutonomousPattern(slotType);
                }
                return;
              }

              if (nextFamily === 'CUSTOM') {
                setPatternFamily(nextFamily);
                setExamType('CUSTOM');
                setPatternGroups(groupsFromQuestions(questions));
                return;
              }

              setPatternFamily(nextFamily);
              setExamType(slotType);
              setPassPercentage(getDefaultPassPercentageForPattern(nextFamily));
              if (!initialExam) {
                applyConfirmedPattern(slotType);
              }
            }}
            className="w-full text-xs bg-white border border-slate-300 rounded px-3 py-1.5 text-slate-900 focus:outline-blue-500"
          >
            <option value="UNIVERSITY">University Pattern</option>
            <option value="AUTONOMOUS">Autonomous Pattern</option>
            <option value="CUSTOM">Custom Pattern</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">
            Pass Percentage (%)
          </label>
          <input
            type="number"
            step="0.1"
            min="1"
            max="100"
            value={passPercentage}
            onChange={(e) => setPassPercentage(parseFloat(e.target.value))}
            className="w-full text-xs bg-white border border-slate-300 rounded px-3 py-1.5 text-slate-900 focus:outline-blue-500 font-mono"
            required
          />
          <div className="text-[10px] text-slate-500 mt-1">
            Rule: CO % &gt; {passPercentage}% → Attainment = 1
          </div>
        </div>
      </div>

      {patternFamily === 'CUSTOM' && (
        <section className="border border-slate-200 rounded-md p-3 space-y-2" aria-label="Custom pattern builder">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wide">Custom Pattern Builder</h3>
            <div className="text-[11px] font-mono text-slate-700 text-right">
              <div>Pattern: {parsedPatternGroups.map((group) => `${group.quantity} × ${group.marksPerQuestion}`).join(' + ') || '—'}</div>
              <div>Questions: {patternQuestions} <span className="mx-1">|</span> Total Marks: {patternTotalMarks}</div>
            </div>
          </div>

          <div className="space-y-1.5">
            {patternGroups.map((group, index) => (
              <div key={index} className="flex items-end gap-2">
                <label className="flex-1 text-[11px] font-medium text-slate-600">
                  Number of Questions
                  <input
                    type="number"
                    min="1"
                    step="1"
                    value={group.quantity}
                    disabled={savedMarksStatus !== 'none'}
                    onChange={(e) => setPatternGroups((current) => current.map((item, itemIndex) =>
                      itemIndex === index ? { ...item, quantity: e.target.value } : item
                    ))}
                    className="mt-0.5 w-full text-xs border border-slate-300 rounded px-2 py-1 text-slate-900"
                  />
                </label>
                <span className="pb-1 text-slate-400">×</span>
                <label className="flex-1 text-[11px] font-medium text-slate-600">
                  Marks per Question
                  <input
                    type="number"
                    min="0.01"
                    step="any"
                    value={group.marksPerQuestion}
                    disabled={savedMarksStatus !== 'none'}
                    onChange={(e) => setPatternGroups((current) => current.map((item, itemIndex) =>
                      itemIndex === index ? { ...item, marksPerQuestion: e.target.value } : item
                    ))}
                    className="mt-0.5 w-full text-xs border border-slate-300 rounded px-2 py-1 font-mono text-slate-900"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => setPatternGroups((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                  disabled={savedMarksStatus !== 'none'}
                  className="cursor-pointer border border-slate-300 rounded px-2 py-1 text-xs text-slate-600 hover:text-red-600 disabled:opacity-40"
                  title="Remove group"
                  aria-label={`Remove group ${index + 1}`}
                >
                  ×
                </button>
                <button
                  type="button"
                  onClick={() => setPatternGroups((current) => {
                    if (index === 0) return current;
                    const reordered = [...current];
                    [reordered[index - 1], reordered[index]] = [reordered[index], reordered[index - 1]];
                    return reordered;
                  })}
                  disabled={savedMarksStatus !== 'none' || index === 0}
                  className="cursor-pointer border border-slate-300 rounded px-2 py-1 text-xs text-slate-600 disabled:opacity-40"
                  title="Move group up"
                  aria-label={`Move group ${index + 1} up`}
                >
                  ↑
                </button>
                <button
                  type="button"
                  onClick={() => setPatternGroups((current) => {
                    if (index >= current.length - 1) return current;
                    const reordered = [...current];
                    [reordered[index], reordered[index + 1]] = [reordered[index + 1], reordered[index]];
                    return reordered;
                  })}
                  disabled={savedMarksStatus !== 'none' || index === patternGroups.length - 1}
                  className="cursor-pointer border border-slate-300 rounded px-2 py-1 text-xs text-slate-600 disabled:opacity-40"
                  title="Move group down"
                  aria-label={`Move group ${index + 1} down`}
                >
                  ↓
                </button>
              </div>
            ))}
          </div>

          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setPatternGroups((current) => [...current, { quantity: '1', marksPerQuestion: '2' }])}
              disabled={savedMarksStatus !== 'none'}
              className="cursor-pointer bg-white border border-slate-300 hover:border-slate-400 text-slate-700 text-xs font-medium px-2.5 py-1 rounded disabled:opacity-40"
            >
              + Add Group
            </button>
            <button
              type="button"
              onClick={generateCustomPattern}
              disabled={savedMarksStatus !== 'none' || !patternIsValid}
              className="cursor-pointer bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold px-3 py-1 rounded disabled:opacity-40"
            >
              Generate Questions
            </button>
          </div>

          <div className="flex max-w-lg gap-2">
            <input
              type="text"
              value={patternName}
              maxLength={100}
              onChange={(e) => setPatternName(e.target.value)}
              placeholder="Saved pattern name"
              aria-label="Saved pattern name"
              disabled={savedMarksStatus !== 'none'}
              className="min-w-0 flex-1 text-xs border border-slate-300 rounded px-2 py-1"
            />
            <button
              type="button"
              onClick={handleSavePattern}
              disabled={savedMarksStatus !== 'none' || !patternName.trim() || !patternIsValid}
              className="cursor-pointer border border-slate-300 bg-white px-2.5 py-1 rounded text-xs font-medium disabled:opacity-40"
            >
              Save Pattern
            </button>
          </div>

          {savedPatterns.length > 0 && (
            <div className="divide-y divide-slate-200 border-t border-slate-200">
              {savedPatterns.map((pattern) => (
                <div key={pattern.id} className="flex items-center justify-between gap-3 py-2 text-xs">
                  <div className="min-w-0">
                    <div className="font-semibold text-slate-800 truncate">{pattern.name}</div>
                    <div className="font-mono text-[11px] text-slate-500">
                      {pattern.groups.map((group) => `${group.quantity} × ${group.marksPerQuestion}`).join(' + ')}
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <button
                      type="button"
                      onClick={() => handleLoadPattern(pattern)}
                      disabled={savedMarksStatus !== 'none'}
                      className="text-blue-700 hover:text-blue-900 font-semibold disabled:opacity-40"
                    >
                      Load
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDeletePattern(pattern)}
                      disabled={savedMarksStatus !== 'none'}
                      className="text-red-700 hover:text-red-900 font-semibold disabled:opacity-40"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {patternFamily === 'UNIVERSITY' && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
          <span className="font-semibold text-slate-700">University Quick Structure:</span>
          <button
            type="button"
            onClick={() => applyConfirmedPattern('INTERNAL_1')}
            className="cursor-pointer bg-slate-100 hover:bg-slate-200 border border-slate-300 text-slate-800 px-2 py-1 rounded text-[11px]"
          >
            Load Internal 1 (50m)
          </button>
          <button
            type="button"
            onClick={() => applyConfirmedPattern('INTERNAL_2')}
            className="cursor-pointer bg-slate-100 hover:bg-slate-200 border border-slate-300 text-slate-800 px-2 py-1 rounded text-[11px]"
          >
            Load Internal 2 (50m)
          </button>
          <button
            type="button"
            onClick={() => applyConfirmedPattern('MODEL')}
            className="cursor-pointer bg-slate-100 hover:bg-slate-200 border border-slate-300 text-slate-800 px-2 py-1 rounded text-[11px]"
          >
            Load Model Exam (60m)
          </button>
          <span className="text-[11px] text-slate-400 italic ml-2">
            *Sets confirmed marks structure; CO mappings are defined below by faculty.
          </span>
        </div>
      )}

      {patternFamily === 'AUTONOMOUS' && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
          <span className="font-semibold text-slate-700">Autonomous Quick Structure:</span>
          <button
            type="button"
            onClick={() => applyAutonomousPattern('INTERNAL_1')}
            className="cursor-pointer bg-slate-100 hover:bg-slate-200 border border-slate-300 text-slate-800 px-2 py-1 rounded text-[11px]"
          >
            Load Internal 1 (50m)
          </button>
          <button
            type="button"
            onClick={() => applyAutonomousPattern('INTERNAL_2')}
            className="cursor-pointer bg-slate-100 hover:bg-slate-200 border border-slate-300 text-slate-800 px-2 py-1 rounded text-[11px]"
          >
            Load Internal 2 (50m)
          </button>
          <button
            type="button"
            onClick={() => applyAutonomousPattern('MODEL')}
            className="cursor-pointer bg-slate-100 hover:bg-slate-200 border border-slate-300 text-slate-800 px-2 py-1 rounded text-[11px]"
          >
            Load Model (100m)
          </button>
        </div>
      )}

      {/* Step 4: Covered COs selection */}
      <div className="bg-slate-50 border border-slate-200 rounded-md p-4">
        <div className="mb-2 flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:justify-between">
          <label className="text-xs font-semibold text-slate-800 uppercase tracking-wide">
            Covered Course Outcomes (COs)
          </label>
          <span className="text-[11px] text-slate-500">
            Select authoritative outcomes covered by this examination
          </span>
        </div>

        <div className="flex flex-wrap gap-2">
          {ALL_COS.map((co) => {
            const isChecked = coveredCOs.includes(co);
            return (
              <label
                key={co}
                className={`flex items-center gap-2 px-3 py-1.5 rounded border text-xs font-semibold cursor-pointer select-none transition-colors ${
                  isChecked
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-100'
                }`}
              >
                <input
                  type="checkbox"
                  checked={isChecked}
                  onChange={() => toggleCO(co)}
                  className="rounded text-blue-600 focus:ring-0"
                />
                {co}
              </label>
            );
          })}
        </div>

        {unmappedCoveredCOs.length > 0 && (
          <div className="mt-2 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-2.5 py-1">
            Note: Every covered CO must have at least one mapped question. Currently unmapped:{' '}
            <span className="font-bold">{unmappedCoveredCOs.join(', ')}</span>
          </div>
        )}
      </div>

      {/* Step 6: Question Configuration Table */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <div>
            <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wide">
              Question Configuration &amp; CO Mapping
            </h3>
            <p className="text-[11px] text-slate-500">
              Each question belongs to exactly one covered CO. Subquestions are aggregated into the question total.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="text-xs font-mono font-semibold text-slate-800">
              Total Questions: <span className="text-blue-600">{questions.length}</span> | Total Marks:{' '}
              <span className="text-blue-600">{totalMarks}</span>
            </div>
            <button
              type="button"
              onClick={handleAddQuestion}
              className="cursor-pointer bg-white border border-slate-300 hover:border-blue-500 text-slate-800 text-xs font-semibold px-2.5 py-1 rounded shadow-2xs transition-colors"
            >
              + Add Question
            </button>
          </div>
        </div>

        <div className="border border-slate-200 rounded overflow-hidden">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-100 text-slate-700 uppercase font-semibold text-[11px] border-b border-slate-200">
              <tr>
                <th className="py-2 px-3 w-16 text-center">#</th>
                <th className="py-2 px-3 w-36">Question No.</th>
                <th className="py-2 px-3 w-36">Max Marks</th>
                <th className="py-2 px-3">Mapped Course Outcome (CO)</th>
                <th className="py-2 px-3 w-16 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 bg-white">
              {questions.map((q, idx) => (
                <tr key={idx} className="hover:bg-slate-50">
                  <td className="py-1.5 px-3 text-center text-slate-400 font-mono">{idx + 1}</td>
                  <td className="py-1.5 px-3">
                    <input
                      type="text"
                      value={q.questionNumber}
                      onChange={(e) =>
                        handleQuestionChange(idx, 'questionNumber', e.target.value)
                      }
                      className="w-full text-xs border border-slate-300 rounded px-2 py-1 font-semibold text-slate-900 focus:outline-blue-500"
                      placeholder="e.g. Q1"
                      required
                    />
                  </td>
                  <td className="py-1.5 px-3">
                    <input
                      type="number"
                      step="0.5"
                      min="0.5"
                      value={q.maxMarks}
                      onChange={(e) =>
                        handleQuestionChange(idx, 'maxMarks', parseFloat(e.target.value) || 0)
                      }
                      className="w-full text-xs border border-slate-300 rounded px-2 py-1 font-mono text-slate-900 focus:outline-blue-500"
                      placeholder="e.g. 2"
                      required
                    />
                  </td>
                  <td className="py-1.5 px-3">
                    <select
                      value={q.coCode}
                      onChange={(e) => handleQuestionChange(idx, 'coCode', e.target.value)}
                      className="w-full text-xs border border-slate-300 rounded px-2 py-1 font-bold text-blue-700 bg-blue-50/50 focus:outline-blue-500 cursor-pointer"
                    >
                      {coveredCOs.map((co) => (
                        <option key={co} value={co}>
                          {co}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="py-1.5 px-3 text-center">
                    <button
                      type="button"
                      onClick={() => handleRemoveQuestion(idx)}
                      disabled={questions.length <= 1}
                      className="cursor-pointer text-slate-400 hover:text-red-600 disabled:opacity-30 disabled:cursor-not-allowed font-bold"
                      title="Remove question"
                    >
                      ×
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      </fieldset>
    </form>
  );
};
