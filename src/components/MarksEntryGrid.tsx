import React, { useState, useEffect, useMemo } from 'react';
import { FileSpreadsheet, FileText } from 'lucide-react';
import {
  ExamDetail,
  Student,
  StudentMarkRecord,
  CanonicalExamResult,
  ExamQuestionConfig,
  ExamCOStatistics,
} from '../types';
import {
  loadExamRoster,
  loadExamQuestions,
  loadExamMarksAndResults,
  saveExamMarks,
  downloadExamExcelReport,
  downloadExamPdfReport,
  MarksValidationError,
} from '../services/marksService';
import { calculateLiveQuestionStatistics } from '../services/questionStatistics';

interface MarksEntryGridProps {
  exam: ExamDetail;
  rosterVersion: number;
}

export const MarksEntryGrid: React.FC<MarksEntryGridProps> = ({ exam, rosterVersion }) => {
  const [configuredQuestions, setConfiguredQuestions] = useState<ExamQuestionConfig[]>(exam.questions);
  const [students, setStudents] = useState<Student[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [downloadingFormat, setDownloadingFormat] = useState<'excel' | 'pdf' | null>(null);
  const [gridData, setGridData] = useState<Record<string, Record<string, string>>>({});
  const [calcResult, setCalcResult] = useState<CanonicalExamResult | null>(null);
  const [questionCoStatistics, setQuestionCoStatistics] = useState<ExamCOStatistics | null>(null);
  const [validationErrors, setValidationErrors] = useState<Record<string, Record<string, string>>>({});
  const [bannerMessage, setBannerMessage] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState<boolean>(false);

  // 1. Sort questions in canonical question-number order
  const sortedQuestions: ExamQuestionConfig[] = useMemo(() => {
    return [...configuredQuestions].sort((a, b) => {
      const numA = parseInt(a.questionNumber.replace(/\D/g, ''), 10);
      const numB = parseInt(b.questionNumber.replace(/\D/g, ''), 10);
      if (!isNaN(numA) && !isNaN(numB)) {
        return numA - numB;
      }
      return a.questionNumber.localeCompare(b.questionNumber, undefined, { numeric: true });
    });
  }, [configuredQuestions]);

  // Questions map for quick lookup of maxMarks
  const questionMap = useMemo(() => {
    const map = new Map<string, ExamQuestionConfig>();
    for (const q of sortedQuestions) {
      map.set(q.questionNumber, q);
    }
    return map;
  }, [sortedQuestions]);

  const liveQuestionStatistics = useMemo(
    () => calculateLiveQuestionStatistics(sortedQuestions, students, gridData),
    [sortedQuestions, students, gridData],
  );

  // Initial load: Roster + Existing saved marks & calculated results
  const loadData = async () => {
    setLoading(true);
    setBannerMessage(null);
    try {
      const apiQuestions = await loadExamQuestions(exam.id);
      const activeQuestions = apiQuestions.length > 0 ? apiQuestions : exam.questions;
      setConfiguredQuestions(activeQuestions);

      // 1. Load students belonging to the exam's selected Department -> Year -> Semester -> Section
      const roster = await loadExamRoster(exam);
      setStudents(roster);

      // 2. Load saved marks & calculated CO results
      const { marks, calculationResult, questionCoStatistics } = await loadExamMarksAndResults(exam.id);

      // Build grid state: registerNo -> questionNumber -> string mark value
      const initialGrid: Record<string, Record<string, string>> = {};
      for (const s of roster) {
        initialGrid[s.registerNo] = {};
        for (const q of activeQuestions.sort((a, b) => {
          const numA = parseInt(a.questionNumber.replace(/\D/g, ''), 10);
          const numB = parseInt(b.questionNumber.replace(/\D/g, ''), 10);
          return !isNaN(numA) && !isNaN(numB) ? numA - numB : a.questionNumber.localeCompare(b.questionNumber, undefined, { numeric: true });
        })) {
          initialGrid[s.registerNo][q.questionNumber] = '';
        }
      }

      for (const m of marks) {
        if (initialGrid[m.registerNo]) {
          initialGrid[m.registerNo][m.questionNumber] = m.obtainedMark.toString();
        }
      }

      setGridData(initialGrid);
      setCalcResult(calculationResult);
      setQuestionCoStatistics(questionCoStatistics);
      setValidationErrors({});
      setHasUnsavedChanges(false);
    } catch (err: any) {
      setBannerMessage({
        text: `Error loading exam marks: ${err.message || 'Unknown error'}`,
        type: 'error',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setConfiguredQuestions(exam.questions);
    setStudents([]);
    setGridData({});
    setCalcResult(null);
    setValidationErrors({});
    setHasUnsavedChanges(false);
    loadData();
  }, [exam.id, rosterVersion]);

  // Cell change handler with strict domain validation (no silent clamping)
  const handleCellChange = (registerNo: string, questionNumber: string, value: string) => {
    setHasUnsavedChanges(true);

    // Update grid mark value as entered by faculty
    setGridData((prev) => ({
      ...prev,
      [registerNo]: {
        ...(prev[registerNo] || {}),
        [questionNumber]: value,
      },
    }));

    // Immediate per-cell validation
    const qConfig = questionMap.get(questionNumber);
    const maxMarks = qConfig ? qConfig.maxMarks : 0;

    let error: string | null = null;
    const trimmed = value.trim();

    if (trimmed !== '') {
      const num = Number(trimmed);
      if (isNaN(num)) {
        error = 'Must be a number';
      } else if (num < 0) {
        error = 'Cannot be negative';
      } else if (num > maxMarks) {
        error = `Exceeds max (${maxMarks})`;
      }
    }

    setValidationErrors((prev) => {
      const studentErrors = { ...(prev[registerNo] || {}) };
      if (error) {
        studentErrors[questionNumber] = error;
      } else {
        delete studentErrors[questionNumber];
      }
      return {
        ...prev,
        [registerNo]: studentErrors,
      };
    });
  };

  // Check if any errors currently exist across the grid
  const hasErrors = useMemo(() => {
    for (const reg in validationErrors) {
      if (Object.keys(validationErrors[reg]).length > 0) {
        return true;
      }
    }
    return false;
  }, [validationErrors]);

  // Explicit Save Action (No Autosave)
  const handleSaveMarks = async () => {
    if (hasErrors) {
      setBannerMessage({
        text: 'Please resolve all highlighted mark validation errors before saving.',
        type: 'error',
      });
      return;
    }

    setSaving(true);
    setBannerMessage(null);

    try {
      const marksToSave: StudentMarkRecord[] = [];
      let missingCount = 0;

      for (const s of students) {
        for (const q of sortedQuestions) {
          const valStr = (gridData[s.registerNo]?.[q.questionNumber] ?? '').trim();
          if (valStr === '') {
            missingCount++;
            continue;
          }
          const numVal = Number(valStr);
          if (isNaN(numVal) || numVal < 0 || numVal > q.maxMarks) {
            throw new MarksValidationError(
              `Invalid mark "${valStr}" for student ${s.registerNo} on question ${q.questionNumber}. ` +
              `Must be numeric, between 0 and ${q.maxMarks}.`
            );
          }
          marksToSave.push({
            registerNo: s.registerNo,
            questionNumber: q.questionNumber,
            obtainedMark: numVal,
          });
        }
      }

      // If marks are missing, warn the user according to Phase 3 incomplete data rules
      const totalRequired = students.length * sortedQuestions.length;
      const isComplete = missingCount === 0;

      const { calculationResult, questionCoStatistics } = await saveExamMarks(
        { ...exam, questions: sortedQuestions },
        students,
        marksToSave,
        isComplete
      );

      setCalcResult(calculationResult);
      setQuestionCoStatistics(questionCoStatistics);
      setHasUnsavedChanges(false);

      if (isComplete) {
        setBannerMessage({
          text: 'Marks saved successfully. CO attainment recalculated using the Phase 3 domain engine.',
          type: 'success',
        });
      } else {
        setBannerMessage({
          text: `Marks saved successfully (${marksToSave.length}/${totalRequired} marks entered). Incomplete marks policy: Full CO attainment requires all question marks to be recorded.`,
          type: 'info',
        });
      }
    } catch (err: any) {
      setBannerMessage({
        text: err.message || 'Failed to save marks.',
        type: 'error',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleDownloadReport = async (format: 'excel' | 'pdf') => {
    setDownloadingFormat(format);
    setBannerMessage(null);

    try {
      if (format === 'excel') {
        await downloadExamExcelReport(exam.id);
      } else {
        await downloadExamPdfReport(exam.id);
      }
      setBannerMessage({
        text: `${format === 'excel' ? 'Excel' : 'PDF'} report downloaded successfully.`,
        type: 'success',
      });
    } catch (err: any) {
      setBannerMessage({
        text: err.message || `Failed to download ${format.toUpperCase()} report.`,
        type: 'error',
      });
    } finally {
      setDownloadingFormat(null);
    }
  };

  if (loading) {
    return (
      <div className="bg-white border border-slate-200 rounded-lg p-8 text-center text-xs text-slate-500 font-medium">
        Loading enrolled student cohort and configured questions...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Banner / Feedback */}
      {bannerMessage && (
        <div
          className={`text-xs px-4 py-3 rounded-md border flex items-center justify-between ${
            bannerMessage.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
              : bannerMessage.type === 'error'
              ? 'bg-rose-50 border-rose-200 text-rose-900'
              : 'bg-amber-50 border-amber-200 text-amber-900'
          }`}
        >
          <div className="flex items-center gap-2">
            <span className="font-bold">
              {bannerMessage.type === 'success' ? '✓' : bannerMessage.type === 'error' ? '⚠' : 'ℹ'}
            </span>
            <span>{bannerMessage.text}</span>
          </div>
          <button
            onClick={() => setBannerMessage(null)}
            className="text-slate-500 hover:text-slate-800 font-bold ml-4 cursor-pointer"
          >
            ✕
          </button>
        </div>
      )}

      {/* Grid Action Toolbar */}
      <div className="bg-white border border-slate-200 rounded-lg p-4 shadow-2xs flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wide">
              Faculty Marks-Entry &amp; CO Attainment Workspace
            </h3>
            {hasUnsavedChanges && (
              <span className="bg-amber-100 text-amber-800 text-[10px] font-bold px-2 py-0.5 rounded">
                Unsaved Changes
              </span>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => handleDownloadReport('excel')}
            disabled={downloadingFormat !== null}
            className="cursor-pointer bg-white border border-slate-300 hover:border-emerald-500 text-slate-700 text-xs font-medium px-3 py-1.5 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
            title="Download Excel report"
          >
            <FileSpreadsheet size={14} aria-hidden="true" />
            {downloadingFormat === 'excel' ? 'Generating...' : 'Download Excel'}
          </button>

          <button
            type="button"
            onClick={() => handleDownloadReport('pdf')}
            disabled={downloadingFormat !== null}
            className="cursor-pointer bg-white border border-slate-300 hover:border-rose-500 text-slate-700 text-xs font-medium px-3 py-1.5 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
            title="Download PDF report"
          >
            <FileText size={14} aria-hidden="true" />
            {downloadingFormat === 'pdf' ? 'Generating...' : 'Download PDF'}
          </button>

          <button
            type="button"
            onClick={loadData}
            disabled={saving}
            className="cursor-pointer bg-white border border-slate-300 hover:border-slate-400 text-slate-700 text-xs font-medium px-3 py-1.5 rounded transition-colors disabled:opacity-50"
          >
            Reload Saved Marks
          </button>

          <button
            type="button"
            onClick={handleSaveMarks}
            disabled={saving || hasErrors}
            className={`cursor-pointer text-xs font-semibold px-4 py-1.5 rounded transition-colors shadow-2xs flex items-center gap-1.5 ${
              hasErrors
                ? 'bg-slate-300 text-slate-500 cursor-not-allowed'
                : 'bg-emerald-700 hover:bg-emerald-800 text-white'
            }`}
          >
            {saving ? 'Saving & Calculating...' : 'Save Marks & Calculate COs'}
          </button>
        </div>
      </div>

      {/* Excel-Like Spreadsheet Grid */}
      <div className="bg-white border border-slate-200 rounded-lg shadow-2xs overflow-hidden">
        <div className="overflow-x-auto max-h-[600px]">
          <table className="marks-entry-table w-full text-left text-xs border-collapse font-sans">
            {/* Table Header */}
            <thead className="bg-slate-100 text-slate-800 sticky top-0 z-10 border-b border-slate-300 text-[11px] select-none">
              {/* Top grouping row */}
              <tr className="border-b border-slate-200 bg-slate-200/70">
                <th
                  colSpan={3}
                  className="py-1.5 px-3 font-bold text-slate-700 text-center border-r border-slate-300 uppercase tracking-wider"
                >
                  Student Identification
                </th>
                <th
                  colSpan={sortedQuestions.length}
                  className="py-1.5 px-3 font-bold text-blue-900 text-center border-r border-slate-300 uppercase tracking-wider bg-blue-50/70"
                >
                  Configured Questions (Faculty Manual Mark Entry)
                </th>
                <th
                  rowSpan={2}
                  className="py-2 px-2 w-16 text-center font-semibold text-slate-900 bg-slate-100 border-r border-slate-300"
                >
                  Total
                </th>
                {exam.coveredCOs.map((co) => (
                  <th
                    key={co}
                    colSpan={4}
                    className="py-1.5 px-2 font-bold text-center border-r border-slate-300 uppercase tracking-wider bg-emerald-50 text-emerald-900"
                  >
                    {co} Results
                  </th>
                ))}
              </tr>

              {/* Specific column headers */}
              <tr className="bg-slate-100 divide-x divide-slate-200">
                <th className="marks-student-index py-2.5 px-2.5 w-12 text-center text-slate-500 font-semibold">#</th>
                <th className="marks-student-register py-2.5 px-3 w-32 font-semibold text-slate-900">Register No</th>
                <th className="marks-student-name py-2.5 px-3 min-w-[160px] font-semibold text-slate-900">Student Name</th>

                {/* Question Columns */}
                {sortedQuestions.map((q) => (
                  <th
                    key={q.questionNumber}
                    className="py-2 px-2 text-center min-w-[76px] bg-blue-50/30 hover:bg-blue-50 transition-colors"
                  >
                    <div className="font-bold text-slate-900">{q.questionNumber}</div>
                    <div className="text-[10px] text-slate-500 font-mono">Max: {q.maxMarks}m</div>
                    <div className="text-[9px] font-bold text-blue-700 uppercase tracking-tight">
                      {q.coCode}
                    </div>
                  </th>
                ))}

                {/* Calculated CO Result Columns for each covered CO */}
                {exam.coveredCOs.map((co) => (
                  <React.Fragment key={co}>
                    <th className="py-2 px-1.5 w-14 text-center text-[10px] font-semibold text-slate-600 bg-emerald-50/40">
                      Max
                    </th>
                    <th className="py-2 px-1.5 w-14 text-center text-[10px] font-semibold text-slate-700 bg-emerald-50/40">
                      Obt
                    </th>
                    <th className="py-2 px-2 w-16 text-center text-[10px] font-semibold text-slate-900 bg-emerald-50/70">
                      CO %
                    </th>
                    <th className="py-2 px-2 w-16 text-center text-[10px] font-bold text-emerald-900 bg-emerald-100/80 border-r border-slate-300">
                      Attain
                    </th>
                  </React.Fragment>
                ))}
              </tr>
            </thead>

            {/* Table Body */}
            <tbody className="divide-y divide-slate-200">
              {students.length === 0 ? (
                <tr>
                  <td
                    colSpan={4 + sortedQuestions.length + exam.coveredCOs.length * 4}
                    className="py-8 text-center text-slate-400 font-medium"
                  >
                    No students found in the selected section cohort.
                  </td>
                </tr>
              ) : (
                students.map((student, sIdx) => {
                  // Find student's calculated result row if available
                  const studentCalc = calcResult?.students?.find(
                    (s) => s.register_no === student.registerNo || (s as any).registerNo === student.registerNo
                  );
                  const getObtainedMarks = (co: string) => {
                    const coRes = studentCalc
                      ? (studentCalc.co_results?.[co] || (studentCalc as any).coResults?.[co])
                      : null;
                    return coRes?.obtained_marks ?? (coRes as any)?.obtainedMarks ?? null;
                  };
                  const co1ObtainedMarks = getObtainedMarks('CO1');
                  const co2ObtainedMarks = getObtainedMarks('CO2');
                  const totalObtained = co1ObtainedMarks !== null && co2ObtainedMarks !== null
                    ? co1ObtainedMarks + co2ObtainedMarks
                    : null;

                  return (
                    <tr
                      key={student.registerNo}
                      className="hover:bg-slate-50/80 transition-colors divide-x divide-slate-200 text-xs"
                    >
                      {/* Row Index */}
                      <td className="marks-student-index py-2 px-2 text-center text-slate-400 font-mono text-[11px]">
                        {sIdx + 1}
                      </td>

                      {/* Register Number */}
                      <td className="marks-student-register py-2 px-3 font-mono font-medium text-slate-800 whitespace-nowrap">
                        {student.registerNo}
                      </td>

                      {/* Student Name */}
                      <td className="marks-student-name py-2 px-3 font-medium text-slate-900 truncate max-w-[200px]" title={student.name}>
                        {student.name}
                      </td>

                      {/* Question Mark Input Cells */}
                      {sortedQuestions.map((q) => {
                        const cellVal = gridData[student.registerNo]?.[q.questionNumber] ?? '';
                        const cellErr = validationErrors[student.registerNo]?.[q.questionNumber];

                        return (
                          <td
                            key={q.questionNumber}
                            className={`p-1 text-center ${
                              cellErr ? 'bg-rose-50' : 'bg-transparent'
                            }`}
                          >
                            <div className="relative">
                              <input
                                type="text"
                                inputMode="decimal"
                                value={cellVal}
                                onChange={(e) =>
                                  handleCellChange(student.registerNo, q.questionNumber, e.target.value)
                                }
                                placeholder="—"
                                className={`w-full py-1 px-1.5 text-center font-mono text-xs rounded border transition-all outline-none ${
                                  cellErr
                                    ? 'border-rose-500 bg-rose-50/50 text-rose-900 font-bold focus:ring-1 focus:ring-rose-500'
                                    : cellVal !== ''
                                    ? 'border-slate-300 bg-white text-slate-900 font-medium focus:border-blue-600 focus:ring-1 focus:ring-blue-600'
                                    : 'border-slate-200 bg-slate-50/50 text-slate-400 focus:bg-white focus:border-blue-600 focus:text-slate-900'
                                }`}
                                title={
                                  cellErr
                                    ? cellErr
                                    : `${student.name} - ${q.questionNumber} (Max: ${q.maxMarks})`
                                }
                              />
                              {cellErr && (
                                <span className="absolute -bottom-3 left-1/2 -translate-x-1/2 text-[9px] font-bold text-rose-600 whitespace-nowrap z-20 bg-white px-1 border border-rose-200 rounded shadow-2xs">
                                  {cellErr}
                                </span>
                              )}
                            </div>
                          </td>
                        );
                      })}

                      <td className="py-2 px-2 text-center font-mono font-semibold text-slate-900 bg-slate-50 border-r border-slate-300">
                        {totalObtained !== null ? totalObtained : '—'}
                      </td>

                      {/* Calculated CO Result Columns */}
                      {exam.coveredCOs.map((co) => {
                        const coRes = studentCalc
                          ? (studentCalc.co_results?.[co] || (studentCalc as any).coResults?.[co])
                          : null;

                        const coMax =
                          coRes?.co_max_marks ??
                          (coRes as any)?.coMaxMarks ??
                          calcResult?.co_max_marks?.[co] ??
                          (calcResult as any)?.coMaxMarks?.[co] ??
                          null;

                        const obtMarks =
                          coRes?.obtained_marks ?? (coRes as any)?.obtainedMarks ?? null;

                        const coPct =
                          coRes?.co_percentage ?? (coRes as any)?.coPercentage ?? null;

                        const attainment = coRes?.attainment ?? null;

                        return (
                          <React.Fragment key={co}>
                            {/* CO Maximum Marks */}
                            <td className="py-2 px-1.5 text-center font-mono text-[11px] text-slate-500 bg-emerald-50/20">
                              {coMax !== null ? coMax : '—'}
                            </td>

                            {/* Student CO Obtained Marks */}
                            <td className="py-2 px-1.5 text-center font-mono font-medium text-slate-800 bg-emerald-50/20">
                              {obtMarks !== null ? obtMarks : '—'}
                            </td>

                            {/* CO Percentage */}
                            <td className="py-2 px-2 text-center font-mono text-[11px] text-slate-800 bg-emerald-50/40">
                              {coPct !== null ? `${Number(coPct).toFixed(1)}%` : '—'}
                            </td>

                            {/* CO Attainment is the authoritative numeric 1/0 result. */}
                            <td className="py-2 px-2 text-center font-mono font-bold text-xs bg-emerald-50/70 border-r border-slate-300">
                              {attainment !== null ? (
                                <span
                                  className={`inline-block px-2 py-0.5 rounded text-[11px] font-bold ${
                                    attainment === 1
                                      ? 'bg-emerald-600 text-white'
                                      : 'bg-slate-200 text-slate-700'
                                  }`}
                                  title={
                                    attainment === 1
                                      ? `${co}: Attained (1) because CO % (${coPct?.toFixed(1)}%) >= Pass % (${exam.passPercentage}%)`
                                      : `${co}: Not Attained (0) because CO % (${coPct?.toFixed(1)}%) <= Pass % (${exam.passPercentage}%)`
                                  }
                                >
                                  {attainment}
                                </span>
                              ) : (
                                <span className="text-slate-300">—</span>
                              )}
                            </td>
                          </React.Fragment>
                        );
                      })}
                    </tr>
                  );
                })
              )}
            </tbody>
            {sortedQuestions.length > 0 && (
              <tfoot className="border-t-2 border-slate-300 bg-slate-50 text-xs">
                {[
                  ['NO OF STUDENTS ≥ 50% MARKS', 'students_at_least_50_percent'],
                  ['NO OF STUDENTS ATTEMPTED', 'students_attempted'],
                  ['% STUDENTS ≥ 50% MARKS', 'percentage_at_least_50_percent'],
                ].map(([label, key]) => (
                  <tr key={label} className="border-b border-slate-200">
                    <td colSpan={3} className="py-2 px-3 font-semibold text-slate-700 whitespace-nowrap">
                      {label}
                    </td>
                    {sortedQuestions.map((question) => {
                      const statistic = liveQuestionStatistics.find(
                        (row) => row.question_number === question.questionNumber
                      );
                      const value = statistic?.[key as keyof typeof statistic];
                      return (
                        <td key={question.questionNumber} className="py-2 px-2 text-center font-mono font-semibold text-slate-800">
                          {value === null || value === undefined
                            ? ''
                            : key === 'percentage_at_least_50_percent'
                            ? `${Number(value).toFixed(2)}%`
                            : value}
                        </td>
                      );
                    })}
                    <td className="py-2 px-2" />
                    <td colSpan={exam.coveredCOs.length * 4} className="py-2 px-2" />
                  </tr>
                ))}
                {questionCoStatistics?.co_averages.map((average) => (
                  <tr key={average.co_code} className="border-b border-slate-200 last:border-b-0">
                    <td colSpan={3} className="py-2 px-3 font-bold text-slate-800 whitespace-nowrap">
                      AVERAGE OF {average.co_code}
                    </td>
                    <td
                      colSpan={sortedQuestions.length + 1 + exam.coveredCOs.length * 4}
                      className="py-2 px-2 font-mono font-bold text-slate-800"
                    >
                      {average.average_percentage === null
                        ? ''
                        : `${Number(average.average_percentage).toFixed(2)}%`}
                    </td>
                  </tr>
                ))}
              </tfoot>
            )}
          </table>
        </div>

        {(() => {
          const overallResults = calcResult?.overall_co_attainment || calcResult?.overallCOAttainment;
          if (!overallResults) return null;
          return (
            <div className="border-t border-slate-200 p-4 bg-emerald-50/30">
              <h4 className="text-xs font-bold uppercase tracking-wide text-slate-800 mb-2">
                Overall CO Attainment
              </h4>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border border-slate-200 bg-white">
                  <thead className="bg-emerald-100/70 text-slate-700 uppercase text-[10px]">
                    <tr>
                      <th className="py-2 px-3">CO</th>
                      <th className="py-2 px-3">Total Students</th>
                      <th className="py-2 px-3">Students Attaining</th>
                      <th className="py-2 px-3">Attainment %</th>
                      <th className="py-2 px-3">Overall Attainment Level</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {Object.entries(overallResults).map(([co, summary]) => {
                      const total = summary.total_students ?? summary.totalStudents ?? 0;
                      const attaining = summary.students_attaining_co ?? summary.studentsAttainingCO ?? 0;
                      const percentage = summary.attainment_percentage ?? summary.attainmentPercentage ?? 0;
                      const level = summary.attainment_level ?? summary.attainmentLevel;
                      return (
                        <tr key={co}>
                          <td className="py-2 px-3 font-bold">{co}</td>
                          <td className="py-2 px-3 font-mono">{total}</td>
                          <td className="py-2 px-3 font-mono">{attaining}</td>
                          <td className="py-2 px-3 font-mono">{Number(percentage).toFixed(1)}%</td>
                          <td className="py-2 px-3 font-mono font-bold">
                            {level === null || level === undefined ? 'Unresolved' : level}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          );
        })()}

        {/* Informative Footnote */}
        <div className="p-3 bg-slate-50 border-t border-slate-200 flex flex-col sm:flex-row sm:items-center sm:justify-between text-[11px] text-slate-500 gap-2">
          <div>
            <span className="font-semibold text-slate-700">Authoritative CO Attainment Rule:</span>{' '}
            <span className="font-mono text-slate-600">
              CO Percentage &gt;= {exam.passPercentage}% → 1, otherwise 0
            </span>{' '}
            (Exact equality with {exam.passPercentage}% produces 1).
          </div>
        </div>
      </div>
    </div>
  );
};
