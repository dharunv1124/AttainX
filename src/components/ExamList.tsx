import React from 'react';
import { ChevronDown } from 'lucide-react';
import { ExamDetail, ExamType, Subject } from '../types';
import { loadSubjects } from '../services/subjectService';
import { formatExamDate } from '../services/examService';

interface ExamListProps {
  exams: ExamDetail[];
  subjects: Subject[];
  onOpenExam: (examId: number, subjectId: number) => void;
  onEditExam: (examId: number, subjectId: number) => void;
  onDeleteExam: (exam: ExamDetail) => void;
  onCreateNew: (subjectId: number, defaultExamName: string, defaultExamType: ExamType) => void;
  selectedDeptId: number;
  selectedYearId: number;
  selectedSemId: number;
  selectedSectionId: number;
  onCreateSubject: (name: string) => Promise<void>;
  onRemoveSubject: (subjectId: number) => Promise<void>;
  onRestoreSubject: (subjectId: number) => Promise<void>;
  onPermanentlyDeleteSubject: (subjectId: number) => Promise<void>;
}

const examSlots: Array<{ types: ExamType[]; label: string; defaultExamName: string; defaultExamType: ExamType }> = [
  { types: ['INTERNAL_1', 'AUTONOMOUS_INTERNAL_1'], label: 'INTERNAL 1', defaultExamName: 'Internal Assessment 1', defaultExamType: 'INTERNAL_1' },
  { types: ['INTERNAL_2', 'AUTONOMOUS_INTERNAL_2'], label: 'INTERNAL 2', defaultExamName: 'Internal Assessment 2', defaultExamType: 'INTERNAL_2' },
  { types: ['MODEL', 'AUTONOMOUS_MODEL'], label: 'MODEL', defaultExamName: 'Model Exam', defaultExamType: 'MODEL' },
];

export const ExamList: React.FC<ExamListProps> = ({
  exams,
  subjects,
  onOpenExam,
  onEditExam,
  onDeleteExam,
  onCreateNew,
  selectedDeptId,
  selectedYearId,
  selectedSemId,
  selectedSectionId,
  onCreateSubject,
  onRemoveSubject,
  onRestoreSubject,
  onPermanentlyDeleteSubject,
}) => {
  const [newSubjectName, setNewSubjectName] = React.useState('');
  const [subjectBusy, setSubjectBusy] = React.useState(false);
  const [subjectMessage, setSubjectMessage] = React.useState<string | null>(null);
  const [showArchivedSubjects, setShowArchivedSubjects] = React.useState(false);
  const [archivedSubjects, setArchivedSubjects] = React.useState<Subject[]>([]);
  const [archivedLoading, setArchivedLoading] = React.useState(false);
  const matchingExams = exams.filter(
    (exam) =>
      exam.departmentId === selectedDeptId &&
      exam.yearId === selectedYearId &&
      exam.semesterId === selectedSemId &&
      exam.sectionId === selectedSectionId
  );

  const findExams = (subjectId: number, slot: (typeof examSlots)[number]) =>
    matchingExams.filter((exam) =>
      exam.subjectId === subjectId && (
        slot.types.includes(exam.examType) ||
        exam.name.trim().toLowerCase() === slot.defaultExamName.toLowerCase()
      )
    );

  const handleCreateSubject = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!newSubjectName.trim()) return;
    setSubjectBusy(true);
    setSubjectMessage(null);
    try {
      await onCreateSubject(newSubjectName.trim());
      setNewSubjectName('');
      setSubjectMessage('Subject added to this semester.');
    } catch (error) {
      setSubjectMessage(error instanceof Error ? error.message : 'Unable to add subject.');
    } finally {
      setSubjectBusy(false);
    }
  };

  const handleRemoveSubject = async (subjectId: number) => {
    setSubjectBusy(true);
    setSubjectMessage(null);
    try {
      await onRemoveSubject(subjectId);
      if (showArchivedSubjects) await refreshArchivedSubjects();
      setSubjectMessage('Subject removed from this semester.');
    } catch (error) {
      setSubjectMessage(error instanceof Error ? error.message : 'Unable to remove subject.');
    } finally {
      setSubjectBusy(false);
    }
  };

  React.useEffect(() => {
    setShowArchivedSubjects(false);
    setArchivedSubjects([]);
    setSubjectMessage(null);
  }, [selectedDeptId, selectedYearId, selectedSemId]);

  const refreshArchivedSubjects = async () => {
    setArchivedLoading(true);
    try {
      const scopedSubjects = await loadSubjects(selectedDeptId, selectedYearId, selectedSemId, true);
      setArchivedSubjects(scopedSubjects.filter((subject) => !subject.isActive));
    } catch (error) {
      setSubjectMessage(error instanceof Error ? error.message : 'Unable to load archived subjects.');
    } finally {
      setArchivedLoading(false);
    }
  };

  const toggleArchivedSubjects = async () => {
    const shouldShow = !showArchivedSubjects;
    setShowArchivedSubjects(shouldShow);
    if (shouldShow) await refreshArchivedSubjects();
  };

  const handleRestoreSubject = async (subjectId: number) => {
    setSubjectBusy(true);
    setSubjectMessage(null);
    try {
      await onRestoreSubject(subjectId);
      setArchivedSubjects((currentSubjects) =>
        currentSubjects.filter((subject) => subject.id !== subjectId),
      );
      setSubjectMessage('Subject recovered to the active list.');
    } catch (error) {
      setSubjectMessage(error instanceof Error ? error.message : 'Unable to recover subject.');
    } finally {
      setSubjectBusy(false);
    }
  };

  const handlePermanentlyDeleteSubject = async (subject: Subject) => {
    const confirmed = window.confirm(
      `Permanently delete ${subject.name} and all of its exams, questions, marks, and Course OBE data? This action cannot be undone.`
    );
    if (!confirmed) return;

    setSubjectBusy(true);
    setSubjectMessage(null);
    try {
      await onPermanentlyDeleteSubject(subject.id);
      setArchivedSubjects((currentSubjects) =>
        currentSubjects.filter((currentSubject) => currentSubject.id !== subject.id),
      );
      setSubjectMessage(`Subject "${subject.name}" was permanently deleted.`);
    } catch (error) {
      setSubjectMessage(error instanceof Error ? error.message : 'Unable to permanently delete subject.');
    } finally {
      setSubjectBusy(false);
    }
  };

  return (
    <section id="exam-section" className="bg-white rounded-lg border border-slate-200 p-4 shadow-2xs">
      <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-2">
        <div>
          <h2 className="text-sm font-semibold text-slate-800 uppercase tracking-wider">SUBJECTS &amp; EXAMS</h2>
          <p className="text-xs text-slate-500 mt-0.5">Available exam records for the selected class and section</p>
        </div>
      </div>

      <form onSubmit={handleCreateSubject} className="mb-3 flex flex-wrap items-end gap-2">
        <label className="text-xs font-medium text-slate-700">
          Add subject to selected semester
          <input
            value={newSubjectName}
            onChange={(event) => setNewSubjectName(event.target.value)}
            maxLength={150}
            required
            className="mt-1 block w-64 max-w-full rounded-md border border-slate-300 px-2.5 py-2 text-xs"
            aria-label="New subject name"
          />
        </label>
        <button
          type="submit"
          disabled={subjectBusy || !newSubjectName.trim()}
          className="rounded-md bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Add Subject
        </button>
        {subjectMessage && <span role="status" className="text-xs text-slate-600">{subjectMessage}</span>}
      </form>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-slate-700 border border-slate-200 rounded">
          <thead className="bg-slate-100 text-slate-800 font-semibold uppercase text-[11px] border-b border-slate-200">
            <tr>
              <th className="py-2.5 px-3">Subject</th>
              {examSlots.map((slot) => <th key={slot.label} className="py-2.5 px-3 text-center">{slot.label}</th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {subjects.map((subject) => (
              <tr key={subject.id} className="hover:bg-slate-50">
                <td className="py-3 px-3 font-semibold text-slate-900 min-w-[240px]">
                  {subject.name}
                  <button
                    type="button"
                    onClick={() => handleRemoveSubject(subject.id)}
                    disabled={subjectBusy}
                    className="ml-3 text-[11px] font-medium text-red-700 hover:text-red-900 disabled:opacity-50"
                  >
                    Remove
                  </button>
                </td>
                {examSlots.map((slot) => {
                  const slotExams = findExams(subject.id, slot);
                  return (
                    <td key={slot.label} className="py-2 px-3 text-center min-w-[150px]">
                      {slotExams.length > 0 ? (
                        <div className="flex flex-col items-center gap-2">
                          {slotExams.map((exam) => (
                            <div key={exam.id} className="flex flex-col items-center gap-1">
                              <span className="font-medium text-slate-800">{exam.name}</span>
                              {formatExamDate(exam.examDate) && (
                                <span className="text-[10px] text-slate-500">
                                  Exam Date: {formatExamDate(exam.examDate)}
                                </span>
                              )}
                              <div className="flex gap-1">
                                <button
                                  type="button"
                                  onClick={() => onOpenExam(exam.id, subject.id)}
                                  className="bg-slate-800 hover:bg-slate-900 text-white text-[11px] font-semibold px-2.5 py-1.5 rounded-md"
                                >
                                  Open Exam
                                </button>
                                <button
                                  type="button"
                                  onClick={() => onEditExam(exam.id, subject.id)}
                                  className="bg-white border border-slate-300 text-slate-700 text-[11px] px-2 py-1.5 rounded-md"
                                >
                                  Edit
                                </button>
                                <button
                                  type="button"
                                  onClick={() => onDeleteExam(exam)}
                                  className="bg-white border border-red-300 text-red-700 hover:border-red-500 text-[11px] px-2 py-1.5 rounded-md"
                                >
                                  Delete
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => onCreateNew(subject.id, slot.defaultExamName, slot.defaultExamType)}
                          className="bg-blue-600 hover:bg-blue-700 text-white text-[11px] font-semibold px-2.5 py-1.5 rounded-md"
                        >
                          Create Exam
                        </button>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 border-t border-slate-200 pt-3">
        <button
          type="button"
          onClick={toggleArchivedSubjects}
          aria-expanded={showArchivedSubjects}
          className="flex w-full items-center justify-between text-left"
        >
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-700">
            Archived Subjects
            {archivedSubjects.length > 0 && <span className="ml-2 text-slate-500">{archivedSubjects.length}</span>}
          </span>
          <ChevronDown aria-hidden="true" className={`h-4 w-4 text-slate-500 ${showArchivedSubjects ? 'rotate-180' : ''}`} />
        </button>
      </div>

      {showArchivedSubjects && (
        <div className="pt-3">
          {archivedLoading ? (
            <p className="text-xs text-slate-500">Loading archived subjects...</p>
          ) : archivedSubjects.length === 0 ? (
            <p className="text-xs text-slate-500">No archived subjects for this semester.</p>
          ) : (
            <div className="overflow-x-auto rounded-md border border-slate-200">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-100 text-[11px] uppercase text-slate-700">
                  <tr>
                    <th className="px-3 py-2">Subject Name</th>
                    <th className="px-3 py-2">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {archivedSubjects.map((subject) => (
                    <tr key={subject.id}>
                      <td className="px-3 py-2">{subject.name}</td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-3">
                          <button
                            type="button"
                            onClick={() => handleRestoreSubject(subject.id)}
                            disabled={subjectBusy}
                            className="font-semibold text-blue-700 hover:text-blue-900 disabled:opacity-50"
                          >
                            Recover
                          </button>
                          <button
                            type="button"
                            onClick={() => void handlePermanentlyDeleteSubject(subject)}
                            disabled={subjectBusy}
                            className="font-semibold text-red-700 hover:text-red-900 disabled:opacity-50"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  );
};
