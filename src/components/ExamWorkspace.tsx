import React, { useState } from 'react';
import { ExamDetail } from '../types';
import { MarksEntryGrid } from './MarksEntryGrid';
import { formatExamDate } from '../services/examService';

const AUTONOMOUS_EXAM_LABELS: Partial<Record<ExamDetail['examType'], string>> = {
  AUTONOMOUS_INTERNAL_1: 'Autonomous Internal 1',
  AUTONOMOUS_INTERNAL_2: 'Autonomous Internal 2',
  AUTONOMOUS_MODEL: 'Autonomous Model',
};

interface ExamWorkspaceProps {
  exam: ExamDetail;
  batchName: string;
  rosterVersion: number;
  studentCount: number;
  showTargetAttainmentReference: boolean;
  onEditConfig: () => void;
  onBackToSelection: () => void;
}

export const ExamWorkspace: React.FC<ExamWorkspaceProps> = ({
  exam,
  batchName,
  rosterVersion,
  studentCount,
  showTargetAttainmentReference,
  onEditConfig,
  onBackToSelection,
}) => {
  const [activeTab, setActiveTab] = useState<'marks' | 'specification'>('marks');

  // Compute distribution per CO
  const coDistribution = exam.coveredCOs.map((co) => {
    const qs = exam.questions.filter((q) => q.coCode === co);
    const marks = qs.reduce((sum, q) => sum + q.maxMarks, 0);
    return {
      co,
      questionCount: qs.length,
      marks,
      questions: qs.map((q) => q.questionNumber),
    };
  });

  return (
    <div className="space-y-4">
      {showTargetAttainmentReference && (
        <section
          aria-labelledby="target-attainment-reference-title"
          className="rounded-md border border-slate-300 bg-white px-4 py-3 text-slate-900"
        >
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <h2
              id="target-attainment-reference-title"
              className="text-xs font-semibold uppercase tracking-wide"
            >
              TARGET FIXING – COURSE OUTCOME ATTAINMENT LEVELS
            </h2>
            <p className="text-xs font-medium">Batch: {batchName}</p>
          </div>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-xs sm:grid-cols-3">
            <div className="flex gap-1">
              <dt className="font-semibold">Level 1:</dt>
              <dd>60% of students scoring 60% and above</dd>
            </div>
            <div className="flex gap-1">
              <dt className="font-semibold">Level 2:</dt>
              <dd>65% of students scoring 60% and above</dd>
            </div>
            <div className="flex gap-1">
              <dt className="font-semibold">Level 3:</dt>
              <dd>70% of students scoring 60% and above</dd>
            </div>
          </dl>
        </section>
      )}

      {/* Workspace Header & Action Bar */}
      <div className="bg-white border border-slate-200 rounded-lg p-5 shadow-2xs">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-200 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="bg-emerald-100 text-emerald-800 text-[11px] font-bold px-2 py-0.5 rounded uppercase tracking-wide">
                Configured &amp; Approved
              </span>
              <span className="text-xs text-slate-400 font-mono">Exam ID: #{exam.id}</span>
            </div>
            <h2 className="text-lg font-bold text-slate-900 mt-1">{exam.name}</h2>
            <p className="text-xs text-slate-500">
              Exam Pattern: <span className="font-semibold text-slate-700">{AUTONOMOUS_EXAM_LABELS[exam.examType] || exam.examType.replace('_', ' ')}</span>
            </p>
            {formatExamDate(exam.examDate) && (
              <p className="text-xs text-slate-500">Exam Date: {formatExamDate(exam.examDate)}</p>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onBackToSelection}
              className="cursor-pointer bg-white border border-slate-300 hover:border-slate-400 text-slate-700 text-xs font-medium px-3 py-2 rounded-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
            >
              ← Back to Exam List
            </button>
            <button
              onClick={onEditConfig}
              className="cursor-pointer bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold px-3 py-2 rounded-md transition-colors shadow-2xs focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
            >
              Edit Configuration
            </button>
          </div>
        </div>

        {/* Hierarchy Context Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 text-xs">
          <div className="bg-slate-50 p-2.5 rounded border border-slate-200">
            <span className="text-slate-500 block text-[11px]">Class &amp; Section</span>
            <span className="font-semibold text-slate-900">
              {exam.departmentCode} · {exam.yearName} · {exam.semesterName} · Section {exam.sectionName}
            </span>
          </div>

          <div className="bg-slate-50 p-2.5 rounded border border-slate-200">
            <span className="text-slate-500 block text-[11px]">Subject</span>
            <span className="font-semibold text-slate-900">{exam.subjectName}</span>
          </div>

          <div className="bg-slate-50 p-2.5 rounded border border-slate-200">
            <span className="text-slate-500 block text-[11px]">Student Count</span>
            <span className="font-bold text-blue-700">{studentCount} Enrolled Students</span>
            <span className="text-[10px] text-slate-400 block">Bound to Section {exam.sectionName}</span>
          </div>

          <div className="bg-slate-50 p-2.5 rounded border border-slate-200">
            <span className="text-slate-500 block text-[11px]">Pass Attainment Threshold</span>
            <span className="font-bold text-emerald-700 font-mono">{exam.passPercentage}%</span>
            <span className="text-[10px] text-slate-500 block">CO % &gt;= {exam.passPercentage}% → Attained</span>
          </div>
        </div>

        {/* Workspace Sub-Navigation */}
        <div className="flex flex-wrap border-b border-slate-200 mt-5 gap-x-6 gap-y-2 text-xs font-medium">
          <button
            onClick={() => setActiveTab('marks')}
            className={`pb-2.5 -mb-px font-semibold cursor-pointer border-b-2 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 ${
              activeTab === 'marks'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            Marks Entry &amp; CO Results Grid
          </button>
          <button
            onClick={() => setActiveTab('specification')}
            className={`pb-2.5 -mb-px font-semibold cursor-pointer border-b-2 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 ${
              activeTab === 'specification'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            Exam Pattern &amp; CO Specification
          </button>
        </div>
      </div>

      {/* Primary Tab: Marks Entry Spreadsheet Grid */}
      {activeTab === 'marks' && <MarksEntryGrid exam={exam} rosterVersion={rosterVersion} />}

      {/* Secondary Tab: Phase 5 Exam Specification & Breakdown */}
      {activeTab === 'specification' && (
        <div className="space-y-4">
          {/* CO Coverage & Distribution Breakdown */}
          <div className="bg-white border border-slate-200 rounded-lg p-5 shadow-2xs">
            <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wide mb-3">
              Course Outcome (CO) Distribution &amp; Weightage
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
              {coDistribution.map((item) => (
                <div
                  key={item.co}
                  className="border border-blue-100 bg-blue-50/40 rounded p-3 flex flex-col justify-between"
                >
                  <div className="flex items-center justify-between">
                    <span className="bg-blue-600 text-white font-bold text-xs px-2 py-0.5 rounded">
                      {item.co}
                    </span>
                    <span className="text-xs font-mono font-bold text-slate-900">
                      {item.marks} Marks (
                      {((item.marks / (exam.totalMarks || 1)) * 100).toFixed(1)}%)
                    </span>
                  </div>
                  <div className="mt-2 pt-2 border-t border-blue-100 text-[11px] text-slate-600">
                    <span>{item.questionCount} Questions: </span>
                    <span className="font-mono text-slate-800 font-medium">
                      {item.questions.join(', ')}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Approved Questions Specification Table */}
          <div className="bg-white border border-slate-200 rounded-lg p-5 shadow-2xs">
            <div className="flex items-center justify-between mb-3 border-b border-slate-100 pb-2">
              <div>
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wide">
                  Approved Question Structure
                </h3>
                <p className="text-[11px] text-slate-500">
                  Total Questions: {exam.totalQuestions} · Total Marks: {exam.totalMarks}
                </p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border border-slate-200 rounded">
                <thead className="bg-slate-100 text-slate-800 font-semibold uppercase text-[11px] border-b border-slate-200">
                  <tr>
                    <th className="py-2 px-3 w-16 text-center">#</th>
                    <th className="py-2 px-4">Question Number</th>
                    <th className="py-2 px-4">Maximum Marks</th>
                    <th className="py-2 px-4">Mapped CO</th>
                    <th className="py-2 px-4">Weightage of Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {exam.questions.map((q, idx) => (
                    <tr key={idx} className="hover:bg-slate-50 transition-colors">
                      <td className="py-2 px-3 text-center text-slate-400 font-mono">{idx + 1}</td>
                      <td className="py-2 px-4 font-semibold text-slate-900">{q.questionNumber}</td>
                      <td className="py-2 px-4 font-mono font-bold text-slate-800">
                        {q.maxMarks} marks
                      </td>
                      <td className="py-2 px-4">
                        <span className="bg-blue-100 text-blue-800 text-[11px] font-bold px-2 py-0.5 rounded">
                          {q.coCode}
                        </span>
                      </td>
                      <td className="py-2 px-4 font-mono text-slate-500 text-[11px]">
                        {((q.maxMarks / (exam.totalMarks || 1)) * 100).toFixed(1)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
