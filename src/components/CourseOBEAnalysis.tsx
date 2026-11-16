import React, { useEffect, useState } from 'react';
import { Download, FileSpreadsheet, FileText } from 'lucide-react';
import { Subject } from '../types';
import { COPOMappingValues, loadCourseCOPOMapping, saveCourseCOPOMapping } from '../services/courseOBEService';
import { downloadCourseOBEExcelReport, downloadCourseOBEPdfReport } from '../services/courseOBEReportService';
import { mergeCourseExamAttainmentDefaults } from '../services/courseOBEAttainmentDefaults';
import {
  CourseCOAttainmentInputRow,
  CourseCOAttainmentResultRow,
  loadCourseExamAttainmentDefaults,
  loadCoursePOAttainment,
  loadCourseOverallCOAttainment,
  saveCourseOverallCOAttainment,
} from '../services/courseOBEAttainmentService';

interface CourseOBEAnalysisProps {
  batchId: number;
  batchName: string;
  departmentName: string;
  departmentId: number;
  yearName: string;
  yearId: number;
  semesterName: string;
  semesterId: number;
  sectionId: number;
  sectionName: string;
  subjects: Subject[];
  selectedSubjectId: number;
  onSubjectChange: (subjectId: number) => void;
}

const courseOutcomes = Array.from({ length: 5 }, (_, index) => `CO${index + 1}`);
const visiblePOIndexes = [...Array.from({ length: 11 }, (_, index) => index), 12, 13];
const poColumns = visiblePOIndexes.map((actualIndex) =>
  actualIndex < 11 ? `PO${actualIndex + 1}` : actualIndex === 12 ? 'PSO1' : 'PSO2',
);

const createEmptyMapping = (): COPOMappingValues =>
  courseOutcomes.map(() => Array.from({ length: 14 }, () => null));

const createEmptyPOAttainment = (): Array<Array<number | null>> =>
  courseOutcomes.map(() => Array.from({ length: 14 }, () => null));

const createEmptyPOAttainmentOverall = (): Array<number | null> =>
  Array.from({ length: 14 }, () => null);

type InputKey = 'a' | 'b' | 'c' | 'university' | 'g';
type ResultKey = keyof CourseCOAttainmentResultRow;

interface ComputationColumn {
  key: string;
  label: string;
  inputKey?: InputKey;
  resultKey?: ResultKey;
}

const computationColumns: ComputationColumn[] = [
  { key: 'a', label: 'A (INT1)', inputKey: 'a' },
  { key: 'b', label: 'B (INT2)', inputKey: 'b' },
  { key: 'c', label: 'C (MODEL)', inputKey: 'c' },
  { key: 'average', label: 'Average', resultKey: 'average' },
  { key: 'attainment', label: 'Attainment', resultKey: 'attainment' },
  { key: 'university', label: 'University', inputKey: 'university' },
  { key: 'university-attainment', label: 'Attainment', resultKey: 'university_attainment' },
  { key: 'd', label: 'D (20%)', resultKey: 'd' },
  { key: 'e', label: 'E (80%)', resultKey: 'e' },
  { key: 'f', label: 'F', resultKey: 'f' },
  { key: 'ninety-f', label: '90% of F', resultKey: 'ninety_percent_f' },
  { key: 'g', label: 'G=IDA', inputKey: 'g' },
  { key: 'ten-g', label: '10% of G', resultKey: 'ten_percent_g' },
  { key: 'overall', label: 'Overall CO', resultKey: 'overall_co' },
];

const averageFormatter = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const createEmptyAttainmentInputs = (): CourseCOAttainmentInputRow[] =>
  courseOutcomes.map(() => ({ a: null, b: null, c: null, university: null, g: null }));

const createEmptyAttainmentResults = (): CourseCOAttainmentResultRow[] =>
  courseOutcomes.map(() => ({
    average: null,
    attainment: null,
    university_attainment: null,
    d: null,
    e: null,
    f: null,
    ninety_percent_f: null,
    ten_percent_g: null,
    overall_co: null,
  }));

const formatCalculatedValue = (key: ResultKey, value: number | null | undefined): string => {
  if (value === null || value === undefined) return '—';
  if (key === 'attainment' || key === 'university_attainment') return String(value);
  if (key === 'average') return averageFormatter.format(value);
  return value.toFixed(2);
};

export const CourseOBEAnalysis: React.FC<CourseOBEAnalysisProps> = ({
  batchId,
  batchName,
  departmentName,
  departmentId,
  yearName,
  yearId,
  semesterName,
  semesterId,
  sectionId,
  sectionName,
  subjects,
  selectedSubjectId,
  onSubjectChange,
}) => {
  const activeSubjects = subjects.filter((subject) => subject.isActive);
  const [mapping, setMapping] = useState<COPOMappingValues>(createEmptyMapping);
  const [loadingMapping, setLoadingMapping] = useState(false);
  const [savingMapping, setSavingMapping] = useState(false);
  const [mappingLoadFailed, setMappingLoadFailed] = useState(false);
  const [mappingMessage, setMappingMessage] = useState<{ text: string; isError: boolean } | null>(null);
  const [attainmentInputs, setAttainmentInputs] = useState<CourseCOAttainmentInputRow[]>(createEmptyAttainmentInputs);
  const [attainmentResults, setAttainmentResults] = useState<CourseCOAttainmentResultRow[]>(createEmptyAttainmentResults);
  const [loadingAttainment, setLoadingAttainment] = useState(false);
  const [savingAttainment, setSavingAttainment] = useState(false);
  const [attainmentLoadFailed, setAttainmentLoadFailed] = useState(false);
  const [attainmentMessage, setAttainmentMessage] = useState<{ text: string; isError: boolean } | null>(null);
  const [poAttainmentValues, setPOAttainmentValues] = useState<Array<Array<number | null>>>(createEmptyPOAttainment);
  const [poAttainmentOverallValues, setPOAttainmentOverallValues] = useState<Array<number | null>>(createEmptyPOAttainmentOverall);
  const [reportFormat, setReportFormat] = useState<'excel' | 'pdf' | null>(null);
  const [reportMessage, setReportMessage] = useState<string | null>(null);

  const refreshPOAttainment = async (subjectId: number) => {
    try {
      const response = await loadCoursePOAttainment(subjectId, sectionId);
      if (subjectId === selectedSubjectId) {
        setPOAttainmentValues(response.values);
        setPOAttainmentOverallValues(response.overall_values);
      }
    } catch {
      if (subjectId === selectedSubjectId) {
        setPOAttainmentValues(createEmptyPOAttainment());
        setPOAttainmentOverallValues(createEmptyPOAttainmentOverall());
      }
    }
  };

  useEffect(() => {
    let active = true;
    setMappingMessage(null);
    setMappingLoadFailed(false);

    if (!selectedSubjectId) {
      setMapping(createEmptyMapping());
      setLoadingMapping(false);
      return () => {
        active = false;
      };
    }

    setMapping(createEmptyMapping());
    setLoadingMapping(true);
    loadCourseCOPOMapping(selectedSubjectId, sectionId)
      .then((values) => {
        if (active) setMapping(values);
      })
      .catch((error: Error) => {
        if (!active) return;
        setMappingLoadFailed(true);
        setMappingMessage({ text: error.message, isError: true });
      })
      .finally(() => {
        if (active) setLoadingMapping(false);
      });

    return () => {
      active = false;
    };
  }, [selectedSubjectId, sectionId]);

  useEffect(() => {
    let active = true;
    setPOAttainmentValues(createEmptyPOAttainment());
    setPOAttainmentOverallValues(createEmptyPOAttainmentOverall());
    if (!selectedSubjectId) return () => { active = false; };

    loadCoursePOAttainment(selectedSubjectId, sectionId)
      .then((response) => {
        if (active) {
          setPOAttainmentValues(response.values);
          setPOAttainmentOverallValues(response.overall_values);
        }
      })
      .catch(() => {
        if (active) {
          setPOAttainmentValues(createEmptyPOAttainment());
          setPOAttainmentOverallValues(createEmptyPOAttainmentOverall());
        }
      });

    return () => {
      active = false;
    };
  }, [selectedSubjectId, sectionId]);

  useEffect(() => {
    let active = true;
    setAttainmentMessage(null);
    setAttainmentLoadFailed(false);

    if (!selectedSubjectId) {
      setAttainmentInputs(createEmptyAttainmentInputs());
      setAttainmentResults(createEmptyAttainmentResults());
      setLoadingAttainment(false);
      return () => {
        active = false;
      };
    }

    setAttainmentInputs(createEmptyAttainmentInputs());
    setAttainmentResults(createEmptyAttainmentResults());
    setLoadingAttainment(true);
    Promise.all([
      loadCourseOverallCOAttainment(selectedSubjectId, sectionId),
      loadCourseExamAttainmentDefaults(
        departmentId,
        yearId,
        semesterId,
        sectionId,
        selectedSubjectId,
        batchId,
      ),
    ])
      .then(([response, examDefaults]) => {
        if (!active) return;
        setAttainmentInputs(mergeCourseExamAttainmentDefaults(response.inputs, examDefaults));
        setAttainmentResults(response.results);
      })
      .catch((error: Error) => {
        if (!active) return;
        setAttainmentLoadFailed(true);
        setAttainmentMessage({ text: error.message, isError: true });
      })
      .finally(() => {
        if (active) setLoadingAttainment(false);
      });

    return () => {
      active = false;
    };
  }, [departmentId, yearId, semesterId, selectedSubjectId, sectionId, batchId]);

  const handleMappingChange = (rowIndex: number, columnIndex: number, value: string) => {
    const cellValue = value === '' ? null : Number(value);
    setMapping((currentMapping) => currentMapping.map((row, currentRowIndex) =>
      currentRowIndex === rowIndex
        ? row.map((currentValue, currentColumnIndex) =>
            currentColumnIndex === columnIndex ? cellValue : currentValue)
        : row,
    ));
  };

  const handleSaveMapping = async () => {
    if (!selectedSubjectId || mappingLoadFailed) return;
    setSavingMapping(true);
    setMappingMessage(null);
    try {
      const savedValues = await saveCourseCOPOMapping(selectedSubjectId, sectionId, mapping);
      setMapping(savedValues);
      await refreshPOAttainment(selectedSubjectId);
      setMappingMessage({ text: 'CO–PO mapping saved.', isError: false });
    } catch (error) {
      setMappingMessage({
        text: error instanceof Error ? error.message : 'Unable to save CO–PO mapping.',
        isError: true,
      });
    } finally {
      setSavingMapping(false);
    }
  };

  const handleRemoveAllMapping = async () => {
    if (!selectedSubjectId || mappingLoadFailed || savingMapping) return;
    if (!window.confirm('Remove all CO–PO mapping data for this subject? This cannot be undone.')) return;

    const subjectId = selectedSubjectId;
    setSavingMapping(true);
    setMappingMessage(null);
    try {
      const savedValues = await saveCourseCOPOMapping(subjectId, sectionId, createEmptyMapping());
      setMapping(savedValues);
      await refreshPOAttainment(subjectId);
      setMappingMessage({ text: 'All CO–PO mapping data removed.', isError: false });
    } catch (error) {
      setMappingMessage({
        text: error instanceof Error ? error.message : 'Unable to remove CO–PO mapping data.',
        isError: true,
      });
    } finally {
      setSavingMapping(false);
    }
  };

  const handleAttainmentInputChange = (rowIndex: number, key: InputKey, value: string) => {
    const numericValue = value === '' ? null : Number(value);
    setAttainmentInputs((currentInputs) => currentInputs.map((row, currentRowIndex) =>
      currentRowIndex === rowIndex ? { ...row, [key]: numericValue } : row,
    ));
  };

  const handleSaveAttainment = async () => {
    if (!selectedSubjectId || attainmentLoadFailed) return;
    setSavingAttainment(true);
    setAttainmentMessage(null);
    try {
      const response = await saveCourseOverallCOAttainment(selectedSubjectId, sectionId, attainmentInputs);
      setAttainmentInputs(response.inputs);
      setAttainmentResults(response.results);
      await refreshPOAttainment(selectedSubjectId);
      setAttainmentMessage({ text: 'Overall CO attainment saved.', isError: false });
    } catch (error) {
      setAttainmentMessage({
        text: error instanceof Error ? error.message : 'Unable to save overall CO attainment.',
        isError: true,
      });
    } finally {
      setSavingAttainment(false);
    }
  };

  const handleRemoveAllAttainmentInputs = async () => {
    if (!selectedSubjectId || attainmentLoadFailed || savingAttainment) return;
    if (!window.confirm('Remove all Overall CO input data for this subject? This cannot be undone.')) return;

    const subjectId = selectedSubjectId;
    setSavingAttainment(true);
    setAttainmentMessage(null);
    try {
      const response = await saveCourseOverallCOAttainment(subjectId, sectionId, createEmptyAttainmentInputs());
      setAttainmentInputs(response.inputs);
      setAttainmentResults(response.results);
      await refreshPOAttainment(subjectId);
      setAttainmentMessage({ text: 'All Overall CO input data removed.', isError: false });
    } catch (error) {
      setAttainmentMessage({
        text: error instanceof Error ? error.message : 'Unable to remove Overall CO input data.',
        isError: true,
      });
    } finally {
      setSavingAttainment(false);
    }
  };

  const handleDownloadReport = async (format: 'excel' | 'pdf') => {
    if (!selectedSubjectId || reportFormat) return;
    setReportFormat(format);
    setReportMessage(null);
    try {
      if (format === 'excel') await downloadCourseOBEExcelReport(selectedSubjectId, sectionId);
      else await downloadCourseOBEPdfReport(selectedSubjectId, sectionId);
    } catch (error) {
      setReportMessage(error instanceof Error ? error.message : `Unable to download ${format.toUpperCase()} report.`);
    } finally {
      setReportFormat(null);
    }
  };

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-2xs">
        <div className="flex flex-col gap-3 border-b border-slate-100 pb-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-800">Course OBE Analysis</h2>
            <p className="mt-1 text-xs text-slate-500">
              {batchName} · {departmentName} · {yearName} · {semesterName} · Section {sectionName || '—'}
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <label className="block text-xs font-medium text-slate-700 sm:w-72">
              Subject
              <select
                value={selectedSubjectId || ''}
                onChange={(event) => onSubjectChange(Number(event.target.value))}
                disabled={activeSubjects.length === 0 || savingMapping || savingAttainment}
                className="mt-1 w-full rounded-md border border-slate-300 bg-slate-50 px-2.5 py-2 text-xs font-medium text-slate-900 focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-60"
              >
                {activeSubjects.length === 0 ? (
                  <option value="">No subjects configured</option>
                ) : (
                  activeSubjects.map((subject) => (
                    <option key={subject.id} value={subject.id}>{subject.name}</option>
                  ))
                )}
              </select>
            </label>
            <button
              type="button"
              onClick={() => handleDownloadReport('excel')}
              disabled={!selectedSubjectId || reportFormat !== null}
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {reportFormat === 'excel' ? <Download size={14} aria-hidden="true" /> : <FileSpreadsheet size={14} aria-hidden="true" />}
              Excel
            </button>
            <button
              type="button"
              onClick={() => handleDownloadReport('pdf')}
              disabled={!selectedSubjectId || reportFormat !== null}
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {reportFormat === 'pdf' ? <Download size={14} aria-hidden="true" /> : <FileText size={14} aria-hidden="true" />}
              PDF
            </button>
            {reportMessage && <span role="alert" className="w-full text-xs text-red-700">{reportMessage}</span>}
          </div>
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-2xs">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-2">
          <h3 className="text-xs font-bold uppercase tracking-wide text-slate-800">CO–PO Mapping</h3>
          <div className="flex flex-wrap items-center gap-3">
            {mappingMessage && (
              <span role="status" className={`text-xs ${mappingMessage.isError ? 'text-red-700' : 'text-emerald-700'}`}>
                {mappingMessage.text}
              </span>
            )}
            <button
              type="button"
              onClick={handleSaveMapping}
              disabled={!selectedSubjectId || loadingMapping || savingMapping || mappingLoadFailed}
              className="rounded-md bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {savingMapping ? 'Saving...' : 'Save Mapping'}
            </button>
            <button
              type="button"
              onClick={handleRemoveAllMapping}
              disabled={!selectedSubjectId || loadingMapping || savingMapping || mappingLoadFailed}
              className="rounded-md border border-red-200 bg-white px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Remove All
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-[1100px] border-collapse text-center text-xs">
            <thead className="bg-slate-100 text-[11px] font-semibold uppercase text-slate-800">
              <tr>
                <th scope="col" className="sticky left-0 z-10 min-w-24 border border-slate-200 bg-slate-100 px-3 py-2">CO</th>
                {poColumns.map((column) => (
                  <th scope="col" key={column} className="min-w-16 border border-slate-200 px-2 py-2">{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {courseOutcomes.map((outcome, rowIndex) => (
                <tr key={outcome}>
                  <th scope="row" className="sticky left-0 z-10 border border-slate-200 bg-slate-50 px-3 py-2 text-left font-semibold text-slate-800">{outcome}</th>
                  {poColumns.map((column, columnIndex) => {
                    const actualColumnIndex = visiblePOIndexes[columnIndex];
                    return (
                    <td key={`${outcome}-${column}`} className="h-9 border border-slate-200 px-2">
                      <select
                        aria-label={`${outcome} ${column} mapping`}
                        value={mapping[rowIndex]?.[actualColumnIndex] ?? ''}
                        onChange={(event) => handleMappingChange(rowIndex, actualColumnIndex, event.target.value)}
                        disabled={loadingMapping || savingMapping || mappingLoadFailed || !selectedSubjectId}
                        className="h-7 w-14 rounded border border-slate-300 bg-white px-1 text-center text-xs text-slate-800 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-slate-100"
                      >
                        <option value="">-</option>
                        <option value="1">1</option>
                        <option value="2">2</option>
                        <option value="3">3</option>
                      </select>
                    </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-2xs">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-2">
          <h3 className="text-xs font-bold uppercase tracking-wide text-slate-800">Computation of Overall CO Attainment in this Course</h3>
          <div className="flex flex-wrap items-center gap-3">
            {attainmentMessage && (
              <span role="status" className={`text-xs ${attainmentMessage.isError ? 'text-red-700' : 'text-emerald-700'}`}>
                {attainmentMessage.text}
              </span>
            )}
            <button
              type="button"
              onClick={handleSaveAttainment}
              disabled={!selectedSubjectId || loadingAttainment || savingAttainment || attainmentLoadFailed}
              className="rounded-md bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {savingAttainment ? 'Saving...' : 'Save Inputs'}
            </button>
            <button
              type="button"
              onClick={handleRemoveAllAttainmentInputs}
              disabled={!selectedSubjectId || loadingAttainment || savingAttainment || attainmentLoadFailed}
              className="rounded-md border border-red-200 bg-white px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Remove All
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-[1800px] border-collapse text-center text-xs">
            <thead className="bg-slate-100 text-[11px] font-semibold text-slate-800">
              <tr>
                <th scope="col" className="sticky left-0 z-20 min-w-20 border border-slate-200 bg-slate-100 px-3 py-2">CO</th>
                {computationColumns.map((column) => (
                  <th scope="col" key={column.key} className="min-w-28 border border-slate-200 px-2 py-2">{column.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {courseOutcomes.map((outcome, rowIndex) => (
                <tr key={outcome}>
                  <th scope="row" className="sticky left-0 z-10 border border-slate-200 bg-slate-50 px-3 py-2 font-semibold text-slate-800">{outcome}</th>
                  {computationColumns.map((column) => (
                    <td
                      key={`${outcome}-${column.key}`}
                      className={`h-10 border border-slate-200 px-2 ${column.inputKey ? 'bg-white' : 'bg-slate-50 font-medium tabular-nums'}`}
                    >
                      {column.inputKey ? (
                        <input
                          type="number"
                          inputMode="decimal"
                          step="any"
                          aria-label={`${outcome} ${column.label}`}
                          value={attainmentInputs[rowIndex]?.[column.inputKey] ?? ''}
                          onChange={(event) => handleAttainmentInputChange(rowIndex, column.inputKey!, event.target.value)}
                          disabled={loadingAttainment || savingAttainment || attainmentLoadFailed || !selectedSubjectId}
                          className="h-7 w-full min-w-16 rounded border border-slate-300 bg-white px-1.5 text-center text-xs tabular-nums text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                        />
                      ) : (
                        <span className="text-slate-700 tabular-nums">
                          {column.resultKey
                            ? formatCalculatedValue(column.resultKey, attainmentResults[rowIndex]?.[column.resultKey])
                            : '—'}
                        </span>
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-2xs">
        <div className="mb-3 border-b border-slate-100 pb-2">
          <h3 className="text-xs font-bold uppercase tracking-wide text-slate-800">PO Attainment</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-[1100px] border-collapse text-center text-xs">
            <thead className="bg-slate-100 text-[11px] font-semibold uppercase text-slate-800">
              <tr>
                <th scope="col" className="sticky left-0 z-10 min-w-20 border border-slate-200 bg-slate-100 px-3 py-2">CO</th>
                {poColumns.map((column) => (
                  <th scope="col" key={column} className="min-w-16 border border-slate-200 px-2 py-2">{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {courseOutcomes.map((outcome, rowIndex) => (
                <tr key={outcome}>
                  <th scope="row" className="sticky left-0 z-10 border border-slate-200 bg-slate-50 px-3 py-2 text-left font-semibold text-slate-800">{outcome}</th>
                  {poColumns.map((column, columnIndex) => {
                    const actualColumnIndex = visiblePOIndexes[columnIndex];
                    return (
                      <td key={`${outcome}-${column}`} className="h-9 border border-slate-200 bg-slate-50 px-2 font-medium tabular-nums text-slate-700" aria-label={`${outcome} ${column} attainment`}>
                        {mapping[rowIndex]?.[actualColumnIndex] == null
                          ? '-'
                          : poAttainmentValues[rowIndex]?.[actualColumnIndex]?.toFixed(2) ?? ''}
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr>
                <th scope="row" className="sticky left-0 z-10 border border-slate-200 bg-slate-100 px-3 py-2 text-left font-bold text-slate-800">Overall</th>
                {poColumns.map((column, columnIndex) => {
                  const actualColumnIndex = visiblePOIndexes[columnIndex];
                  return (
                    <td key={`overall-${column}`} className="h-9 border border-slate-200 bg-slate-100 px-2 font-bold tabular-nums text-slate-800" aria-label={`Overall ${column} attainment`}>
                      {poAttainmentOverallValues[actualColumnIndex]?.toFixed(2) ?? ''}
                    </td>
                  );
                })}
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};