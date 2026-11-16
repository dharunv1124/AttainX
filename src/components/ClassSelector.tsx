import React, { useEffect, useRef, useState } from 'react';
import { Batch, Department, Year, Semester, Section } from '../types';
import type { DeletionStatus, SectionDeletionStatus } from '../services/academicService';

interface ClassSelectorProps {
  batches: Batch[];
  selectedBatchId: number;
  onBatchChange: (id: number) => void;
  onBatchCreate: (name: string) => Promise<void>;
  onBatchDelete: (id: number) => Promise<void>;
  getBatchDeletionStatus: (id: number) => Promise<DeletionStatus>;
  getSectionDeletionStatus: (id: number) => Promise<SectionDeletionStatus>;
  departments: Department[];
  years: Year[];
  semesters: Semester[];
  sections: Section[];
  selectedDeptId: number;
  selectedYearId: number;
  selectedSemId: number;
  selectedSectionId: number;
  onDeptChange: (id: number) => void;
  onYearChange: (id: number) => void;
  onSemChange: (id: number) => void;
  onSectionChange: (id: number) => void;
  onSectionAdd: (name: string) => Promise<void>;
  onSectionRemove: (id: number, planToken: string) => Promise<void>;
}

type DeleteDialogTarget =
  | { kind: 'batch'; id: number }
  | { kind: 'section'; id: number; batchId: number; departmentId: number; yearId: number };

const normalizeBatchName = (name: string) => name.trim().replace(/[-–—]/g, '-');

export const ClassSelector: React.FC<ClassSelectorProps> = ({
  batches,
  selectedBatchId,
  onBatchChange,
  onBatchCreate,
  onBatchDelete,
  getBatchDeletionStatus,
  getSectionDeletionStatus,
  departments,
  years,
  semesters,
  sections,
  selectedDeptId,
  selectedYearId,
  selectedSemId,
  selectedSectionId,
  onDeptChange,
  onYearChange,
  onSemChange,
  onSectionChange,
  onSectionAdd,
  onSectionRemove,
}) => {
  const [newSectionName, setNewSectionName] = useState('');
  const [sectionMessage, setSectionMessage] = useState<string | null>(null);
  const [batchMessage, setBatchMessage] = useState<string | null>(null);
  const [sectionAction, setSectionAction] = useState<'add' | 'remove' | null>(null);
  const batchActionLock = useRef(false);
  const sectionActionLock = useRef(false);
  const [showBatchForm, setShowBatchForm] = useState(false);
  const [batchName, setBatchName] = useState('');
  const [deleteConfirmation, setDeleteConfirmation] = useState('');
  const [deleteDialogTarget, setDeleteDialogTarget] = useState<DeleteDialogTarget | null>(null);
  const [batchAction, setBatchAction] = useState(false);
  const [batchDeletionStatus, setBatchDeletionStatus] = useState<DeletionStatus | null>(null);
  const [batchStatusLoading, setBatchStatusLoading] = useState(false);
  const [showSectionManagement, setShowSectionManagement] = useState(false);
  const [sectionDeletionStatus, setSectionDeletionStatus] = useState<SectionDeletionStatus | null>(null);
  const [sectionStatusLoading, setSectionStatusLoading] = useState(false);

  // Filter semesters based on Year
  const availableSemesters = semesters.filter((s) => s.yearId === selectedYearId);

  // Filter sections based on Department and Year
  const availableSections = sections.filter(
    (s) =>
      s.batchId === selectedBatchId &&
      s.departmentId === selectedDeptId &&
      s.yearId === selectedYearId
  );
  const selectedSection = availableSections.find((section) => section.id === selectedSectionId);
  const sectionBatchName = batches.find((batch) => batch.id === selectedSection?.batchId)?.batchName || 'Unknown';
  const sectionDepartmentName = departments.find((department) => department.id === selectedSection?.departmentId)?.name || 'Unknown';
  const sectionYearName = years.find((year) => year.id === selectedSection?.yearId)?.name || 'Unknown';
  const sectionSemesterName = semesters.find((semester) => semester.id === selectedSemId)?.name || 'Unknown';
  const selectedBatch = batches.find((batch) => batch.id === selectedBatchId);
  const deletingBatch = deleteDialogTarget?.kind === 'batch'
    ? batches.find((batch) => batch.id === deleteDialogTarget.id)
    : undefined;
  const deletingSection = deleteDialogTarget?.kind === 'section'
    ? sections.find((section) => section.id === deleteDialogTarget.id)
    : undefined;
  const confirmationMatches = deleteDialogTarget?.kind === 'batch' && deletingBatch
    ? normalizeBatchName(deleteConfirmation) === normalizeBatchName(deletingBatch.batchName)
    : deleteDialogTarget?.kind === 'section' && deletingSection
      ? deleteConfirmation === 'CONFIRM DELETE'
      : false;
  const deleteActionInProgress = deleteDialogTarget?.kind === 'batch'
    ? batchAction
    : sectionAction === 'remove';
  const deleteDialogMessage = deleteDialogTarget?.kind === 'batch' ? batchMessage : sectionMessage;

  useEffect(() => {
    if (!deleteDialogTarget) return;
    const selectionChanged = deleteDialogTarget.kind === 'batch'
      ? deleteDialogTarget.id !== selectedBatchId
      : deleteDialogTarget.id !== selectedSectionId ||
        deleteDialogTarget.batchId !== selectedBatchId ||
        deleteDialogTarget.departmentId !== selectedDeptId ||
        deleteDialogTarget.yearId !== selectedYearId;
    if (selectionChanged) {
      setDeleteDialogTarget(null);
      setDeleteConfirmation('');
    }
  }, [deleteDialogTarget, selectedBatchId, selectedDeptId, selectedSectionId, selectedYearId]);

  useEffect(() => {
    if (!showBatchForm) return;
    setBatchDeletionStatus(null);
    setDeleteConfirmation('');
    setBatchMessage(null);
    if (!selectedBatchId) {
      setBatchStatusLoading(false);
      return;
    }
    let active = true;
    setBatchStatusLoading(true);
    void getBatchDeletionStatus(selectedBatchId)
      .then((result) => {
        if (active) setBatchDeletionStatus(result);
      })
      .catch((error: unknown) => {
        if (active) {
          setBatchDeletionStatus({
            can_delete: false,
            reason: error instanceof Error ? error.message : 'Unable to verify batch data.',
          });
        }
      })
      .finally(() => {
        if (active) setBatchStatusLoading(false);
      });
    return () => {
      active = false;
    };
  }, [getBatchDeletionStatus, selectedBatchId, showBatchForm]);

  useEffect(() => {
    if (!showSectionManagement || !selectedSectionId) {
      setSectionDeletionStatus(null);
      return;
    }
    let active = true;
    setSectionStatusLoading(true);
    void getSectionDeletionStatus(selectedSectionId)
      .then((result) => {
        if (active) setSectionDeletionStatus(result);
      })
      .catch((error: unknown) => {
        if (active) {
          setSectionDeletionStatus(null);
          setSectionMessage(error instanceof Error ? error.message : 'Unable to verify section data.');
        }
      })
      .finally(() => {
        if (active) setSectionStatusLoading(false);
      });
    return () => {
      active = false;
    };
  }, [getSectionDeletionStatus, selectedSectionId, showSectionManagement]);

  const handleCreateBatch = async (event: React.FormEvent) => {
    event.preventDefault();
    if (batchActionLock.current) return;
    if (!batchName.trim()) {
      setBatchMessage('Enter batch in the format 2025–29.');
      return;
    }
    batchActionLock.current = true;
    setBatchAction(true);
    setBatchMessage(null);
    try {
      await onBatchCreate(batchName.trim());
      setBatchName('');
      setShowBatchForm(false);
      setBatchMessage('Batch added. Select its academic structure to continue.');
    } catch (error) {
      setBatchMessage(error instanceof Error ? error.message : 'Unable to add batch.');
    } finally {
      batchActionLock.current = false;
      setBatchAction(false);
    }
  };

  const handleAddSection = async (event: React.FormEvent) => {
    event.preventDefault();
    if (sectionActionLock.current) return;
    const name = newSectionName.trim();
    if (!name) {
      setSectionMessage('Enter a section name.');
      return;
    }

  sectionActionLock.current = true;
    setSectionAction('add');
    setSectionMessage(null);
    try {
      await onSectionAdd(name);
      setNewSectionName('');
      setSectionDeletionStatus(null);
      setSectionMessage(`Section ${name.toUpperCase()} added.`);
    } catch (error) {
      setSectionMessage(error instanceof Error ? error.message : 'Unable to add section.');
    } finally {
      sectionActionLock.current = false;
      setSectionAction(null);
    }
  };

  const handleRemoveSection = async () => {
    if (sectionActionLock.current) return;
    if (deleteDialogTarget?.kind !== 'section' || !selectedSection || deleteDialogTarget.id !== selectedSection.id) return;
    if (!sectionDeletionStatus?.can_delete || !sectionDeletionStatus.plan_token) {
      setSectionMessage(sectionDeletionStatus?.reason || 'Section is being verified.');
      return;
    }
    if (deleteConfirmation !== 'CONFIRM DELETE') {
      setSectionMessage('Type CONFIRM DELETE to continue.');
      return;
    }
    sectionActionLock.current = true;
    setSectionAction('remove');
    setSectionMessage(null);
    try {
      await onSectionRemove(deleteDialogTarget.id, sectionDeletionStatus.plan_token);
      setSectionDeletionStatus(null);
      setDeleteDialogTarget(null);
      setDeleteConfirmation('');
      setSectionMessage(`Section ${selectedSection.name} permanently deleted.`);
    } catch (error) {
      setSectionMessage(error instanceof Error ? error.message : 'Unable to remove section.');
    } finally {
      sectionActionLock.current = false;
      setSectionAction(null);
    }
  };

  const handleRemoveBatch = async () => {
    if (batchActionLock.current) return;
    if (deleteDialogTarget?.kind !== 'batch') return;
    const batch = batches.find((item) => item.id === deleteDialogTarget.id);
    if (!batch) return;
    if (!batchDeletionStatus?.can_delete) {
      setBatchMessage(batchDeletionStatus?.reason || 'Batch data is still being checked.');
      return;
    }
    if (!confirmationMatches) {
      setBatchMessage('Batch name did not match. Nothing was deleted.');
      return;
    }

    batchActionLock.current = true;
    setBatchAction(true);
    setBatchMessage(null);
    try {
      await onBatchDelete(batch.id);
      setBatchDeletionStatus(null);
      setDeleteConfirmation('');
      setDeleteDialogTarget(null);
      setBatchMessage(`Batch ${batch.batchName} deleted.`);
    } catch (error) {
      const detail = error instanceof Error ? error.message : 'Unknown error.';
      setBatchMessage(`Unable to delete batch: ${detail}`);
    } finally {
      batchActionLock.current = false;
      setBatchAction(false);
    }
  };

  const handleOpenSectionDeleteDialog = async () => {
    if (!selectedSection) return;
    setSectionMessage(null);
    setDeleteConfirmation('');
    setSectionStatusLoading(true);
    try {
      const currentStatus = await getSectionDeletionStatus(selectedSection.id);
      setSectionDeletionStatus(currentStatus);
      if (!currentStatus.can_delete) {
        setSectionMessage(currentStatus.reason || 'Unable to verify Section data.');
        return;
      }
      setDeleteDialogTarget({
        kind: 'section',
        id: selectedSection.id,
        batchId: selectedBatchId,
        departmentId: selectedDeptId,
        yearId: selectedYearId,
      });
    } catch (error) {
      setSectionMessage(error instanceof Error ? error.message : 'Unable to verify Section data.');
    } finally {
      setSectionStatusLoading(false);
    }
  };

  const handleOpenBatchDeleteDialog = () => {
    if (!selectedBatch) return;
    setBatchMessage(null);
    setDeleteConfirmation('');
    setDeleteDialogTarget({ kind: 'batch', id: selectedBatch.id });
  };

  const handleCancelDelete = () => {
    if (deleteDialogTarget?.kind === 'batch') setBatchMessage(null);
    if (deleteDialogTarget?.kind === 'section') setSectionMessage(null);
    setDeleteDialogTarget(null);
    setDeleteConfirmation('');
  };

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-2xs">
      <div className="flex items-center justify-between mb-3 border-b border-slate-100 pb-2">
        <h2 className="text-sm font-semibold text-slate-800 uppercase tracking-wider">
          CLASS &amp; STUDENTS
        </h2>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3">
        {/* Batch */}
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">Batch</label>
          <select
            value={selectedBatchId}
            onChange={(event) => onBatchChange(Number(event.target.value))}
            className="w-full text-xs bg-slate-50 border border-slate-300 rounded-md px-2.5 py-2 text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-medium"
          >
            {batches.filter((batch) => batch.isActive).map((batch) => (
              <option key={batch.id} value={batch.id}>{batch.batchName}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => {
              setDeleteDialogTarget(null);
              setDeleteConfirmation('');
              setShowBatchForm((visible) => !visible);
              setBatchMessage(null);
            }}
            className="mt-2 text-[11px] font-semibold text-blue-700 hover:text-blue-900"
          >
            {showBatchForm ? 'Close batch management' : 'Manage batches'}
          </button>
        </div>

        {/* Department */}
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">Department</label>
          <select
            value={selectedDeptId}
            onChange={(e) => onDeptChange(Number(e.target.value))}
            className="w-full text-xs bg-slate-50 border border-slate-300 rounded-md px-2.5 py-2 text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-medium"
          >
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.code} - {d.name}
              </option>
            ))}
          </select>
        </div>

        {/* Year */}
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">Academic Year</label>
          <select
            value={selectedYearId}
            onChange={(e) => onYearChange(Number(e.target.value))}
            className="w-full text-xs bg-slate-50 border border-slate-300 rounded-md px-2.5 py-2 text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-medium"
          >
            {years.map((y) => (
              <option key={y.id} value={y.id}>
                {y.name}
              </option>
            ))}
          </select>
        </div>

        {/* Semester */}
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">Semester</label>
          <select
            value={selectedSemId}
            onChange={(e) => onSemChange(Number(e.target.value))}
            className="w-full text-xs bg-slate-50 border border-slate-300 rounded-md px-2.5 py-2 text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-medium"
          >
            {availableSemesters.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>

        {/* Section */}
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">Section</label>
          <select
            value={selectedSectionId}
            onChange={(e) => onSectionChange(Number(e.target.value))}
            className="w-full text-xs bg-slate-50 border border-slate-300 rounded-md px-2.5 py-2 text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-medium"
          >
            {availableSections.length > 0 &&
              !availableSections.some((section) => section.id === selectedSectionId) && (
                <option value={0}>No matching section selected</option>
              )}
            {availableSections.length > 0 ? (
              availableSections.map((sec) => (
                <option key={sec.id} value={sec.id}>
                  Section {sec.name}
                </option>
              ))
            ) : (
              <option value={0}>No section configured</option>
            )}
          </select>
          <button
            type="button"
            onClick={() => {
              setShowSectionManagement((open) => !open);
              setSectionMessage(null);
            }}
            className="mt-2 text-[11px] font-semibold text-blue-700 hover:text-blue-900"
          >
            {showSectionManagement ? 'Close section management' : 'Section Management'}
          </button>
        </div>
      </div>

      {(showBatchForm || showSectionManagement) && (
        <div className={`mt-3 grid grid-cols-1 gap-3 ${showBatchForm && showSectionManagement ? 'md:grid-cols-2' : ''}`}>
          {showBatchForm && (
            <div className="min-w-0 space-y-3 rounded-md border border-slate-200 bg-slate-50 p-3">
              <form onSubmit={handleCreateBatch} className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
                <input
                  value={batchName}
                  onChange={(event) => setBatchName(event.target.value)}
                  maxLength={50}
                  placeholder="Batch name (e.g. 2025–29)"
                  aria-label="New Batch name"
                  className="w-full min-w-0 rounded border border-slate-300 px-2.5 py-2 text-xs"
                />
                <button
                  type="submit"
                  disabled={batchAction || !batchName.trim()}
                  className="rounded bg-blue-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
                >
                  {batchAction ? 'Adding...' : 'Add Batch'}
                </button>
              </form>
              <div className="space-y-2 border-t border-slate-200 pt-3">
                <p className="text-xs font-medium text-slate-700">
                  Batch to delete: <span className="font-semibold text-slate-900">{selectedBatch?.batchName || 'No Batch selected'}</span>
                </p>
                <p className="text-[11px] text-slate-600">
                  {batchStatusLoading ? 'Checking batch…' : batchDeletionStatus?.reason || 'Permanent deletion removes this batch and its owned academic data.'}
                </p>
                <button
                  type="button"
                  onClick={handleOpenBatchDeleteDialog}
                  disabled={!selectedBatch || batchAction || batchStatusLoading || !batchDeletionStatus?.can_delete}
                  className="w-full rounded border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 disabled:opacity-50"
                >
                  Delete selected batch
                </button>
              </div>
              {batchMessage && <p role="status" className="text-xs text-slate-700">{batchMessage}</p>}
            </div>
          )}

          {showSectionManagement && (
            <div className="min-w-0 space-y-3 rounded-md border border-slate-200 bg-slate-50 p-3">
              <form onSubmit={handleAddSection} className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
                <input
                  value={newSectionName}
                  onChange={(event) => setNewSectionName(event.target.value)}
                  maxLength={20}
                  placeholder="New section"
                  aria-label="New section name"
                  className="w-full min-w-0 rounded border border-slate-300 px-2.5 py-2 text-xs"
                />
                <button
                  type="submit"
                  disabled={sectionAction !== null || !selectedDeptId || !selectedYearId}
                  className="rounded bg-blue-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
                >
                  {sectionAction === 'add' ? 'Adding...' : 'Add Section'}
                </button>
              </form>
              <div className="flex flex-col gap-2 border-t border-slate-200 pt-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-[11px] text-slate-600">
                  {sectionStatusLoading
                    ? 'Checking section…'
                    : sectionDeletionStatus?.reason || 'Permanent deletion removes this section and its owned academic data.'}
                </p>
                <button
                  type="button"
                  onClick={handleOpenSectionDeleteDialog}
                  disabled={
                    !selectedSection ||
                    sectionAction !== null ||
                    sectionStatusLoading ||
                    !sectionDeletionStatus?.can_delete ||
                    !sectionDeletionStatus.plan_token
                  }
                  className="shrink-0 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 disabled:opacity-50"
                >
                  {sectionAction === 'remove' ? 'Deleting...' : 'Delete Section'}
                </button>
              </div>
              {sectionMessage && <p role="status" className="text-xs text-slate-700">{sectionMessage}</p>}
            </div>
          )}
        </div>
      )}
      {batchMessage && !showBatchForm && (
        <p role="status" className="mt-2 text-xs text-slate-700">{batchMessage}</p>
      )}

      {deleteDialogTarget && (deletingBatch || deletingSection) && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/50 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-dialog-title"
            className="w-full max-w-lg space-y-4 rounded-lg border border-slate-200 bg-white p-5 shadow-2xl"
          >
            <div className="space-y-2">
              <h3 id="delete-dialog-title" className="text-base font-semibold text-slate-900">
                Confirm permanent deletion
              </h3>
              {deletingBatch ? (
                <p className="text-sm leading-5 text-slate-700">
                  Batch <span className="font-semibold text-slate-900">{deletingBatch.batchName}</span> will be permanently deleted along with its owned students, sections, subjects, exams, marks, and Course OBE data. This cannot be undone.
                </p>
              ) : deletingSection ? (
                <>
                  <p className="text-sm leading-5 text-slate-700">
                    Section <span className="font-semibold text-slate-900">{deletingSection.name}</span> and the records below will be permanently deleted. Students actively assigned to another Section will be preserved. This cannot be undone.
                  </p>
                  <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs text-slate-600">
                    <dt>Batch</dt><dd>{sectionBatchName}</dd>
                    <dt>Department</dt><dd>{sectionDepartmentName}</dd>
                    <dt>Year</dt><dd>{sectionYearName}</dd>
                    <dt>Semester</dt><dd>{sectionSemesterName}</dd>
                  </dl>
                  {sectionStatusLoading || !sectionDeletionStatus ? (
                    <p className="text-sm text-slate-600">Refreshing deletion preview…</p>
                  ) : (
                    <>
                      <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 rounded border border-red-100 bg-red-50 p-3 text-xs text-slate-700">
                        <dt>Students</dt><dd>{sectionDeletionStatus.student_count}</dd>
                        <dt>Academic placements</dt><dd>{sectionDeletionStatus.placement_count}</dd>
                        <dt>Student marks</dt><dd>{sectionDeletionStatus.student_mark_count}</dd>
                        <dt>Exams</dt><dd>{sectionDeletionStatus.exam_count}</dd>
                        <dt>Exam questions</dt><dd>{sectionDeletionStatus.exam_question_count}</dd>
                        <dt>Exam covered CO records</dt><dd>{sectionDeletionStatus.exam_covered_co_count}</dd>
                        <dt>Section CO–PO mappings</dt><dd>{sectionDeletionStatus.course_co_po_mapping_count}</dd>
                        <dt>Section CO attainment inputs</dt><dd>{sectionDeletionStatus.course_co_attainment_input_count}</dd>
                      </dl>
                      <details className="text-xs text-slate-700">
                        <summary className="cursor-pointer font-medium">
                          Student IDs to delete ({sectionDeletionStatus.student_ids_to_delete.length})
                        </summary>
                        <p className="mt-1 break-words">
                          {sectionDeletionStatus.student_ids_to_delete.join(', ') || 'None'}
                        </p>
                      </details>
                      {sectionDeletionStatus.student_ids_preserved.length > 0 && (
                        <details className="text-xs text-slate-700">
                          <summary className="cursor-pointer font-medium">
                            Section-linked students preserved because assigned elsewhere ({sectionDeletionStatus.student_ids_preserved.length})
                          </summary>
                          <p className="mt-1 break-words">
                            {sectionDeletionStatus.student_ids_preserved.join(', ')}
                          </p>
                        </details>
                      )}
                    </>
                  )}
                </>
              ) : null}
            </div>
            <label className="block space-y-1 text-xs font-medium text-slate-700" htmlFor="delete-confirmation-input">
              {deletingBatch ? (
                <>Type <span className="font-semibold">{deletingBatch.batchName}</span>; dash style and surrounding spaces may differ.</>
              ) : (
                <>Type <span className="font-semibold">CONFIRM DELETE</span> to continue.</>
              )}
              <input
                id="delete-confirmation-input"
                value={deleteConfirmation}
                onChange={(event) => {
                  setDeleteConfirmation(event.target.value);
                  if (deleteDialogTarget.kind === 'batch') setBatchMessage(null);
                  else setSectionMessage(null);
                }}
                maxLength={deletingBatch ? 50 : 30}
                autoComplete="off"
                placeholder={deletingBatch ? 'Enter the selected Batch name' : 'Type CONFIRM DELETE'}
                className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-200"
              />
            </label>
            {deleteDialogMessage && (
              <p role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                {deleteDialogMessage}
              </p>
            )}
            <div className="flex justify-end gap-2 border-t border-slate-100 pt-3">
              <button
                type="button"
                onClick={handleCancelDelete}
                disabled={deleteActionInProgress}
                className="rounded border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void (deleteDialogTarget.kind === 'batch' ? handleRemoveBatch() : handleRemoveSection())}
                disabled={
                  deleteActionInProgress ||
                  !confirmationMatches ||
                  (deletingSection && (!sectionDeletionStatus?.plan_token || sectionStatusLoading))
                }
                className="rounded bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
              >
                {deleteActionInProgress ? 'Deleting…' : 'Confirm Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};
