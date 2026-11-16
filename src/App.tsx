import React, { useState, useEffect, useRef } from 'react';
import { Batch, Department, ExamDetail, ExamType, Section, Semester, Student, Subject, Year } from './types';
import { deleteExam, loadExamById, loadExamSavedMarkCount, loadExamsFromApi } from './services/examService';
import {
  createBatch,
  createSection,
  deleteBatch,
  deleteSection,
  getBatchDeletionStatus,
  getSectionDeletionStatus,
  loadBatches,
  loadDepartments,
  loadSections,
  loadSemesters,
  loadYears,
} from './services/academicService';
import { Header } from './components/Header';
import { ClassSelector } from './components/ClassSelector';
import { ExamList } from './components/ExamList';
import { ExamForm } from './components/ExamForm';
import { ExamWorkspace } from './components/ExamWorkspace';
import { StudentManagement } from './components/StudentManagement';
import { loadSectionStudents } from './services/studentService';
import {
  createSubject,
  loadSubjects,
  permanentlyDeleteArchivedSubject,
  removeSubject,
  restoreSubject,
} from './services/subjectService';
import { CourseOBEAnalysis } from './components/CourseOBEAnalysis';

type AppView = 'list' | 'create' | 'edit' | 'workspace' | 'course-obe';

interface PersistedAppUiState {
  batchId?: number;
  departmentId?: number;
  yearId?: number;
  semesterId?: number;
  sectionId?: number;
  subjectId?: number;
  view?: AppView;
  currentExamId?: number;
  newExamName?: string;
  newExamType?: ExamType;
}

const APP_UI_STATE_KEY = 'copo-app-ui-state-v1';
const batchYearKey = (batchId: number, yearId: number) => `${batchId}:${yearId}`;
const sectionContextKey = (batchId: number, departmentId: number, yearId: number) =>
  `${batchId}:${departmentId}:${yearId}`;
const APP_VIEWS: AppView[] = ['list', 'create', 'edit', 'workspace', 'course-obe'];
const EXAM_TYPES: ExamType[] = [
  'INTERNAL_1',
  'INTERNAL_2',
  'MODEL',
  'CUSTOM',
  'AUTONOMOUS_INTERNAL_1',
  'AUTONOMOUS_INTERNAL_2',
  'AUTONOMOUS_MODEL',
];

function readPersistedAppUiState(): PersistedAppUiState | null {
  try {
    const rawState = localStorage.getItem(APP_UI_STATE_KEY);
    if (!rawState) return null;
    const parsed = JSON.parse(rawState);
    const readId = (value: unknown) => Number.isSafeInteger(value) && Number(value) > 0
      ? Number(value)
      : undefined;

    return {
      batchId: readId(parsed.batchId),
      departmentId: readId(parsed.departmentId),
      yearId: readId(parsed.yearId),
      semesterId: readId(parsed.semesterId),
      sectionId: readId(parsed.sectionId),
      subjectId: readId(parsed.subjectId),
      view: APP_VIEWS.includes(parsed.view) ? parsed.view : 'list',
      currentExamId: readId(parsed.currentExamId),
      newExamName: typeof parsed.newExamName === 'string' ? parsed.newExamName : undefined,
      newExamType: EXAM_TYPES.includes(parsed.newExamType) ? parsed.newExamType : undefined,
    };
  } catch {
    return null;
  }
}

export default function App() {

  // Master Data selections
  const [departments, setDepartments] = useState<Department[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [years, setYears] = useState<Year[]>([]);
  const [semesters, setSemesters] = useState<Semester[]>([]);
  const [sections, setSections] = useState<Section[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);

  // Selected class & subject state
  const [selectedDeptId, setSelectedDeptId] = useState<number>(1);
  const [selectedBatchId, setSelectedBatchId] = useState<number>(0);
  const [selectedYearId, setSelectedYearId] = useState<number>(3);
  const [selectedSemId, setSelectedSemId] = useState<number>(5);
  const [selectedSectionId, setSelectedSectionId] = useState<number>(0);
  const [selectedSubjectId, setSelectedSubjectId] = useState<number>(0);
  const [newExamName, setNewExamName] = useState('Internal Assessment 1');
  const [newExamType, setNewExamType] = useState<ExamType>('INTERNAL_1');
  const [savedUiState] = useState(readPersistedAppUiState);
  const [uiStateReady, setUiStateReady] = useState(false);

  // Exams state
  const [exams, setExams] = useState<ExamDetail[]>([]);
  const [currentExam, setCurrentExam] = useState<ExamDetail | null>(null);
  const [students, setStudents] = useState<Student[]>([]);
  const [studentsLoading, setStudentsLoading] = useState(true);
  const [rosterVersion, setRosterVersion] = useState(0);

  // View state: 'list' | 'create' | 'edit' | 'workspace'
  const [view, setView] = useState<AppView>('list');
  const [flashMessage, setFlashMessage] = useState<{
    text: string;
    type: 'success' | 'error';
  } | null>(null);
  const yearByBatchRef = useRef(new Map<number, number>());
  const semesterByBatchYearRef = useRef(new Map<string, number>());
  const sectionNameByContextRef = useRef(new Map<string, string>());
  const homeScrollYRef = useRef<number | null>(null);

  const rememberCurrentAcademicSelection = () => {
    if (selectedBatchId && selectedYearId) {
      yearByBatchRef.current.set(selectedBatchId, selectedYearId);
      semesterByBatchYearRef.current.set(
        batchYearKey(selectedBatchId, selectedYearId),
        selectedSemId,
      );
    }

    const contextKey = sectionContextKey(selectedBatchId, selectedDeptId, selectedYearId);
    const sectionName = sections.find((section) => section.id === selectedSectionId)?.name
      || sectionNameByContextRef.current.get(contextKey);
    if (sectionName) sectionNameByContextRef.current.set(contextKey, sectionName);
    return sectionName;
  };

  const captureHomeScrollPosition = () => {
    if (homeScrollYRef.current === null) homeScrollYRef.current = window.scrollY;
  };

  useEffect(() => {
    const savedScrollY = homeScrollYRef.current;
    if (view !== 'list' || savedScrollY === null) return;

    const frame = window.requestAnimationFrame(() => {
      const maxScrollY = document.documentElement.scrollHeight - window.innerHeight;
      if (savedScrollY <= maxScrollY) {
        window.scrollTo(0, savedScrollY);
      } else {
        document.getElementById('exam-section')?.scrollIntoView({ block: 'start' });
      }
      homeScrollYRef.current = null;
    });

    return () => window.cancelAnimationFrame(frame);
  }, [view]);

  useEffect(() => {
    let active = true;
    const initializeAppState = async () => {
      try {
        const loadedBatches = await loadBatches();
        if (!active) return;
        setBatches(loadedBatches);
        const activeBatches = loadedBatches.filter((item) => item.isActive);
        const batch = activeBatches.find((item) => item.id === savedUiState?.batchId)
          || activeBatches.find((item) => item.isDefault)
          || activeBatches[0];
        const batchId = batch?.id || 0;
        setSelectedBatchId(batchId);
        const [loadedDepartments, loadedYears, loadedSemesters, loadedExams] = await Promise.all([
          loadDepartments(),
          loadYears(),
          loadSemesters(),
          loadExamsFromApi({ batchId }),
        ]);
        if (!active) return;

        setDepartments(loadedDepartments);
        setYears(loadedYears);
        setSemesters(loadedSemesters);
        setExams(loadedExams);

        const department = loadedDepartments.find((item) => item.id === savedUiState?.departmentId)
          || loadedDepartments.find((item) => item.code === 'CSE')
          || loadedDepartments[0];
        const departmentId = department?.id || 0;
        setSelectedDeptId(departmentId);

        const year = loadedYears.find((item) => item.id === savedUiState?.yearId)
          || loadedYears.find((item) => item.yearNumber === 3)
          || loadedYears[0];
        const yearId = year?.id || 0;
        setSelectedYearId(yearId);

        const availableSemesters = loadedSemesters.filter((item) => item.yearId === yearId);
        const semester = availableSemesters.find((item) => item.id === savedUiState?.semesterId)
          || availableSemesters.find((item) => item.semesterNumber === 5)
          || availableSemesters[0];
        const semesterId = semester?.id || 0;
        setSelectedSemId(semesterId);
        if (batchId && yearId) {
          yearByBatchRef.current.set(batchId, yearId);
          semesterByBatchYearRef.current.set(batchYearKey(batchId, yearId), semesterId);
        }

        const loadedSections = batchId
          ? await loadSections(undefined, undefined, batchId)
          : [];
        if (!active) return;
        setSections(loadedSections);
        const section = loadedSections.find((item) =>
          item.id === savedUiState?.sectionId &&
          item.batchId === batchId &&
          item.departmentId === departmentId &&
          item.yearId === yearId
        )
          || loadedSections.find((item) =>
            item.name === 'A' &&
            item.batchId === batchId &&
            item.departmentId === departmentId &&
            item.yearId === yearId
          )
          || loadedSections.find((item) =>
            item.batchId === batchId &&
            item.departmentId === departmentId &&
            item.yearId === yearId
          );
        const sectionId = section?.id || 0;
        setSelectedSectionId(sectionId);
        if (section) {
          sectionNameByContextRef.current.set(
            sectionContextKey(batchId, departmentId, yearId),
            section.name,
          );
        }

        const loadedSubjects = departmentId && yearId && semesterId
          ? await loadSubjects(departmentId, yearId, semesterId, false, batchId)
          : [];
        if (!active) return;
        setSubjects(loadedSubjects);
        const subject = loadedSubjects.find((item) => item.id === savedUiState?.subjectId && item.isActive)
          || loadedSubjects.find((item) => item.isActive);
        const subjectId = subject?.id || 0;
        setSelectedSubjectId(subjectId);

        setNewExamName(savedUiState?.newExamName || 'Internal Assessment 1');
        setNewExamType(savedUiState?.newExamType || 'INTERNAL_1');

        const requestedView = savedUiState?.view || 'list';
        const savedExam = savedUiState?.currentExamId
          ? loadedExams.find((item) => item.id === savedUiState.currentExamId)
          : undefined;
        const examContextMatches = savedExam &&
          savedExam.batchId === batchId &&
          savedExam.departmentId === departmentId &&
          savedExam.yearId === yearId &&
          savedExam.semesterId === semesterId &&
          savedExam.sectionId === sectionId &&
          savedExam.subjectId === subjectId;

        if ((requestedView === 'workspace' || requestedView === 'edit') && examContextMatches) {
          setCurrentExam(savedExam);
          setView(requestedView);
        } else if (requestedView === 'workspace' || requestedView === 'edit') {
          setCurrentExam(null);
          setView('list');
        } else {
          setCurrentExam(null);
          setView(requestedView);
        }
      } catch (error) {
        if (active) setFlashMessage({
          text: error instanceof Error ? error.message : 'Unable to restore application state.',
          type: 'error',
        });
      } finally {
        if (active) setUiStateReady(true);
      }
    };

    void initializeAppState();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!uiStateReady) return;
    try {
      localStorage.setItem(APP_UI_STATE_KEY, JSON.stringify({
        batchId: selectedBatchId,
        departmentId: selectedDeptId,
        yearId: selectedYearId,
        semesterId: selectedSemId,
        sectionId: selectedSectionId,
        subjectId: selectedSubjectId,
        view,
        currentExamId: view === 'workspace' || view === 'edit' ? currentExam?.id : undefined,
        newExamName,
        newExamType,
      } satisfies PersistedAppUiState));
    } catch {
      // Keep the current session usable when browser storage is unavailable.
    }
  }, [
    uiStateReady,
    selectedDeptId,
    selectedBatchId,
    selectedYearId,
    selectedSemId,
    selectedSectionId,
    selectedSubjectId,
    view,
    currentExam,
    newExamName,
    newExamType,
  ]);

  useEffect(() => {
    if (!uiStateReady) return;
    if (!selectedBatchId) {
      setExams([]);
      return;
    }
    let active = true;
    loadExamsFromApi({ batchId: selectedBatchId })
      .then((loadedExams) => {
        if (active) setExams(loadedExams);
      })
      .catch((error: Error) => {
        if (active) setFlashMessage({ text: error.message, type: 'error' });
      });
    return () => {
      active = false;
    };
  }, [uiStateReady, selectedBatchId]);

  useEffect(() => {
    if (!uiStateReady) return;
    if (!selectedDeptId || !selectedYearId) {
      setSections([]);
      setSelectedSectionId(0);
      return;
    }

    let active = true;
    loadSections(undefined, undefined, selectedBatchId)
      .then((loadedSections) => {
        if (!active) return;
        setSections(loadedSections);
        const contextSections = loadedSections.filter((section) =>
          section.batchId === selectedBatchId &&
          section.departmentId === selectedDeptId &&
          section.yearId === selectedYearId
        );
        const contextKey = sectionContextKey(selectedBatchId, selectedDeptId, selectedYearId);
        const preferredSectionName = sectionNameByContextRef.current.get(contextKey);
        const matchingSection = preferredSectionName
          ? contextSections.find((section) => section.name === preferredSectionName)
          : contextSections.find((section) => section.name === 'A') || contextSections[0];
        setSelectedSectionId(matchingSection?.id || 0);
        if (matchingSection) {
          sectionNameByContextRef.current.set(contextKey, matchingSection.name);
        } else if (preferredSectionName) {
          setFlashMessage({
            text: `Section ${preferredSectionName} is not configured for the selected batch, department, and year. Choose an available section or add one in Section Management.`,
            type: 'error',
          });
        }
      })
      .catch((error: Error) => {
        if (!active) return;
        setSections([]);
        setSelectedSectionId(0);
        setFlashMessage({ text: error.message, type: 'error' });
      });

    return () => {
      active = false;
    };
  }, [uiStateReady, selectedBatchId, selectedDeptId, selectedYearId]);

  useEffect(() => {
    if (!uiStateReady) return;
    if (!selectedDeptId || !selectedYearId || !selectedSemId) {
      setSubjects([]);
      setSelectedSubjectId(0);
      return;
    }

    let active = true;
    loadSubjects(selectedDeptId, selectedYearId, selectedSemId, false, selectedBatchId)
      .then((loadedSubjects) => {
        if (!active) return;

        setSubjects(loadedSubjects);
        setSelectedSubjectId((currentSubjectId) => {
          if (loadedSubjects.some((subject) => subject.id === currentSubjectId && subject.isActive)) {
            return currentSubjectId;
          }
          return loadedSubjects.find((subject) => subject.isActive)?.id || 0;
        });
      })
      .catch((error: Error) => {
        if (active) {
          setSubjects([]);
          setSelectedSubjectId(0);
          setFlashMessage({ text: error.message, type: 'error' });
        }
      });

    return () => {
      active = false;
    };
  }, [uiStateReady, selectedBatchId, selectedDeptId, selectedYearId, selectedSemId]);

  const refreshStudents = async () => {
    setStudentsLoading(true);
    try {
      setStudents(await loadSectionStudents(selectedSectionId));
    } catch (error) {
      setStudents([]);
      setFlashMessage({
        text: error instanceof Error ? error.message : 'Unable to load section students.',
        type: 'error',
      });
    } finally {
      setStudentsLoading(false);
    }
  };

  useEffect(() => {
    if (!uiStateReady) return;
    if (!selectedSectionId) {
      setStudents([]);
      setStudentsLoading(false);
      return;
    }
    refreshStudents();
  }, [uiStateReady, selectedSectionId]);

  const handleYearChange = (yearId: number) => {
    const currentSectionName = rememberCurrentAcademicSelection();
    const nextContextKey = sectionContextKey(selectedBatchId, selectedDeptId, yearId);
    if (!sectionNameByContextRef.current.has(nextContextKey) && currentSectionName) {
      sectionNameByContextRef.current.set(nextContextKey, currentSectionName);
    }
    setSelectedYearId(yearId);
    yearByBatchRef.current.set(selectedBatchId, yearId);
    const validSemesters = semesters.filter((semester) => semester.yearId === yearId);
    const rememberedSemesterId = semesterByBatchYearRef.current.get(batchYearKey(selectedBatchId, yearId));
    const nextSemester = validSemesters.find((semester) => semester.id === rememberedSemesterId)
      || validSemesters[0];
    setSelectedSemId(nextSemester?.id || 0);
    setSelectedSectionId(0);
    setFlashMessage(null);
    if (view !== 'course-obe') handleReturnHome();
  };

  const handleSemChange = (semId: number) => {
    setSelectedSemId(semId);
    semesterByBatchYearRef.current.set(batchYearKey(selectedBatchId, selectedYearId), semId);
    if (view !== 'course-obe') handleReturnHome();
  };

  const handleDeptChange = (deptId: number) => {
    rememberCurrentAcademicSelection();
    setSelectedDeptId(deptId);
    setSelectedSectionId(0);
    if (view !== 'course-obe') handleReturnHome();
  };

  const handleBatchChange = (batchId: number) => {
    if (!batchId || batchId === selectedBatchId) return;
    const currentSectionName = rememberCurrentAcademicSelection();
    const nextYearId = years.find((year) => year.id === yearByBatchRef.current.get(batchId))?.id
      || years.find((year) => year.id === selectedYearId)?.id
      || years.find((year) => year.yearNumber === 3)?.id
      || years[0]?.id
      || 0;
    const nextDepartmentId = departments.find((department) => department.code === 'CSE')?.id
      || departments[0]?.id
      || 0;
    const nextContextKey = sectionContextKey(batchId, nextDepartmentId, nextYearId);
    if (
      !sectionNameByContextRef.current.has(nextContextKey) &&
      currentSectionName &&
      nextDepartmentId === selectedDeptId
    ) {
      sectionNameByContextRef.current.set(nextContextKey, currentSectionName);
    }
    const validSemesters = semesters.filter((semester) => semester.yearId === nextYearId);
    const rememberedSemesterId = semesterByBatchYearRef.current.get(batchYearKey(batchId, nextYearId));
    const nextSemester = validSemesters.find((semester) => semester.id === rememberedSemesterId)
      || validSemesters.find((semester) => semester.id === selectedSemId)
      || validSemesters[0];

    setSelectedBatchId(batchId);
    setSelectedDeptId(nextDepartmentId);
    setSelectedYearId(nextYearId);
    yearByBatchRef.current.set(batchId, nextYearId);
    setSelectedSemId(nextSemester?.id || 0);
    if (nextSemester) {
      semesterByBatchYearRef.current.set(batchYearKey(batchId, nextYearId), nextSemester.id);
    }
    setSelectedSectionId(0);
    setFlashMessage(null);
    setSelectedSubjectId(0);
    setSections([]);
    setSubjects([]);
    setExams([]);
    setCurrentExam(null);
    setView('list');
  };

  const handleSectionChange = (sectionId: number) => {
    const section = sections.find((item) =>
      item.id === sectionId &&
      item.batchId === selectedBatchId &&
      item.departmentId === selectedDeptId &&
      item.yearId === selectedYearId
    );
    if (section) {
      sectionNameByContextRef.current.set(
        sectionContextKey(selectedBatchId, selectedDeptId, selectedYearId),
        section.name,
      );
    }
    setSelectedSectionId(section?.id || 0);
  };

  const handleBatchCreate = async (batchName: string) => {
    const batch = await createBatch(batchName);
    setBatches((current) => [...current, batch].sort((left, right) => left.startYear - right.startYear));
    handleBatchChange(batch.id);
  };

  const handleBatchDelete = async (batchId: number) => {
    await deleteBatch(batchId);
    try {
      localStorage.removeItem(APP_UI_STATE_KEY);
    } catch {
      // The current session can continue if browser storage is unavailable.
    }
    const remainingBatches = batches.filter((batch) => batch.id !== batchId);
    setBatches(remainingBatches);
    const fallback = remainingBatches.find((batch) => batch.isDefault) || remainingBatches[0];
    if (batchId === selectedBatchId) {
      const departmentId = departments.find((department) => department.code === 'CSE')?.id || departments[0]?.id || 0;
      const yearId = years.find((year) => year.yearNumber === 3)?.id || years[0]?.id || 0;
      const semesterId = semesters.find((semester) => semester.semesterNumber === 5 && semester.yearId === yearId)?.id
        || semesters.find((semester) => semester.yearId === yearId)?.id
        || 0;
      setSelectedBatchId(fallback?.id || 0);
      setSelectedDeptId(departmentId);
      setSelectedYearId(yearId);
      setSelectedSemId(semesterId);
      setSelectedSectionId(0);
      setSelectedSubjectId(0);
      setSections([]);
      setSubjects([]);
      setExams([]);
      setCurrentExam(null);
      setStudents([]);
      setView('list');
    }
    const refreshedBatches = await loadBatches();
    setBatches(refreshedBatches);
    if (batchId === selectedBatchId && fallback) {
      setSections(await loadSections(undefined, undefined, fallback.id));
    }
  };

  const handleSaveSuccess = (saved: ExamDetail) => {
    setExams((previous) => [saved, ...previous.filter((exam) => exam.id !== saved.id)]);
    setCurrentExam(saved);
    setView('workspace');
    setFlashMessage({
      text: `Exam configuration for "${saved.name}" saved and verified successfully.`,
      type: 'success',
    });
    setTimeout(() => setFlashMessage(null), 4000);
  };

  const handleStudentAdded = async () => {
    await refreshStudents();
    setRosterVersion((version) => version + 1);
  };

  const handleSectionAdd = async (name: string) => {
    const createdSection = await createSection(selectedDeptId, selectedYearId, selectedBatchId, name);
    setSections((currentSections) =>
      [...currentSections, createdSection].sort((left, right) => left.name.localeCompare(right.name)),
    );
    sectionNameByContextRef.current.set(
      sectionContextKey(selectedBatchId, selectedDeptId, selectedYearId),
      createdSection.name,
    );
    setSelectedSectionId(createdSection.id);
  };

  const handleSectionRemove = async (sectionId: number, planToken: string) => {
    await deleteSection(sectionId, planToken);
    try {
      localStorage.removeItem(APP_UI_STATE_KEY);
    } catch {
      // The current session can continue if browser storage is unavailable.
    }
    const cachedSections = sections.filter((section) => section.id !== sectionId);
    setSections(cachedSections);
    const availableCachedSections = cachedSections.filter(
      (section) =>
        section.batchId === selectedBatchId &&
        section.departmentId === selectedDeptId &&
        section.yearId === selectedYearId,
    );
    if (selectedSectionId === sectionId) {
      const nextSection = availableCachedSections[0];
      setSelectedSectionId(nextSection?.id || 0);
      const contextKey = sectionContextKey(selectedBatchId, selectedDeptId, selectedYearId);
      if (nextSection) {
        sectionNameByContextRef.current.set(contextKey, nextSection.name);
      } else {
        sectionNameByContextRef.current.delete(contextKey);
      }
      setStudents([]);
    }
    setSelectedSubjectId(0);
    setSubjects([]);
    setExams((currentExams) => currentExams.filter((exam) => exam.sectionId !== sectionId));
    if (currentExam?.sectionId === sectionId) {
      setCurrentExam(null);
      setView('list');
    }
    const [remainingSections, refreshedSubjects] = await Promise.all([
      loadSections(undefined, undefined, selectedBatchId),
      loadSubjects(selectedDeptId, selectedYearId, selectedSemId, false, selectedBatchId),
    ]);
    setSections(remainingSections);
    setSubjects(refreshedSubjects);
    setSelectedSubjectId(refreshedSubjects.find((subject) => subject.isActive)?.id || 0);
  };

  const refreshSubjects = async () => {
    const loadedSubjects = await loadSubjects(selectedDeptId, selectedYearId, selectedSemId, false, selectedBatchId);
    setSubjects(loadedSubjects);
    setSelectedSubjectId((currentSubjectId) =>
      loadedSubjects.some((subject) => subject.id === currentSubjectId && subject.isActive)
        ? currentSubjectId
        : (loadedSubjects.find((subject) => subject.isActive)?.id || 0),
    );
  };

  const handleCreateSubject = async (name: string) => {
    await createSubject(name, selectedDeptId, selectedYearId, selectedSemId, selectedBatchId);
    await refreshSubjects();
  };

  const handleRemoveSubject = async (subjectId: number) => {
    await removeSubject(subjectId);
    await refreshSubjects();
  };

  const handleRestoreSubject = async (subjectId: number) => {
    await restoreSubject(subjectId, selectedDeptId, selectedYearId, selectedSemId, selectedBatchId);
    await refreshSubjects();
  };

  const handlePermanentlyDeleteSubject = async (subjectId: number) => {
    await permanentlyDeleteArchivedSubject(subjectId);
  };

  const loadExamContext = async (examId: number, rowSubjectId: number, destination: 'workspace' | 'edit') => {
    if (view === 'list') captureHomeScrollPosition();
    setFlashMessage(null);
    try {
      const exam = await loadExamById(examId);
      if (exam.id !== examId || exam.subjectId !== rowSubjectId) {
        throw new Error('This exam does not match the selected subject row in the saved backend data.');
      }

      const [loadedSections, loadedSubjects] = await Promise.all([
        loadSections(undefined, undefined, exam.batchId),
        loadSubjects(exam.departmentId, exam.yearId, exam.semesterId, false, exam.batchId),
      ]);
      if (exam.batchId !== selectedBatchId) handleBatchChange(exam.batchId);
      setSections(loadedSections);
      setSubjects(loadedSubjects);
      setSelectedDeptId(exam.departmentId);
      setSelectedYearId(exam.yearId);
      setSelectedSemId(exam.semesterId);
      setSelectedSectionId(exam.sectionId);
      setSelectedSubjectId(exam.subjectId);
      setExams((currentExams) => [exam, ...currentExams.filter((currentExam) => currentExam.id !== exam.id)]);
      setCurrentExam(exam);
      setView(destination);
    } catch (error) {
      if (view === 'list') homeScrollYRef.current = null;
      setFlashMessage({
        text: error instanceof Error ? error.message : 'Unable to load the selected exam.',
        type: 'error',
      });
    }
  };

  const handleReturnHome = () => {
    setCurrentExam(null);
    setNewExamName('Internal Assessment 1');
    setNewExamType('INTERNAL_1');
    setView('list');
  };

  const handleDeleteExam = async (exam: ExamDetail) => {
    try {
      const savedMarkCount = await loadExamSavedMarkCount(exam.id);
      const confirmation =
        `Exam: ${exam.name}\n\n` +
        'Are you sure you want to permanently delete this exam and all marks recorded for it? This action cannot be undone.' +
        (savedMarkCount > 0
          ? `\n\nWarning: ${savedMarkCount} recorded mark${savedMarkCount === 1 ? '' : 's'} will also be permanently deleted.`
          : '');

      if (!window.confirm(confirmation)) return;

      await deleteExam(exam.id);
      setExams((currentExams) => currentExams.filter((currentExam) => currentExam.id !== exam.id));
      setFlashMessage({ text: `Exam "${exam.name}" was deleted.`, type: 'success' });
    } catch (error) {
      setFlashMessage({
        text: error instanceof Error ? error.message : 'Unable to delete exam.',
        type: 'error',
      });
    }
  };

  return (
    <div className="app-shell min-h-screen bg-slate-100 text-slate-900 flex flex-col font-sans">
      <Header
        onNavigateHome={handleReturnHome}
        onNavigateOBEAnalysis={() => setView('course-obe')}
        showCourseOBEButton={view === 'list'}
      />

      <main className="app-main flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 space-y-4">
        {/* Flash Message Banner */}
        {flashMessage && (
          <div
            role={flashMessage.type === 'error' ? 'alert' : 'status'}
            className={`border text-xs px-4 py-2.5 rounded-md flex items-center justify-between ${
              flashMessage.type === 'error'
                ? 'bg-red-50 border-red-200 text-red-900'
                : 'bg-emerald-50 border-emerald-200 text-emerald-900'
            }`}
          >
            <div className="flex items-center gap-2">
              <span className="font-bold">{flashMessage.type === 'error' ? '!' : '✓'}</span>
              <span>{flashMessage.text}</span>
            </div>
            <button
              onClick={() => setFlashMessage(null)}
              aria-label="Dismiss notification"
              className={`font-bold ml-4 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 rounded ${
                flashMessage.type === 'error'
                  ? 'text-red-700 hover:text-red-900 focus-visible:ring-red-600'
                  : 'text-emerald-700 hover:text-emerald-900 focus-visible:ring-emerald-600'
              }`}
            >
              ✕
            </button>
          </div>
        )}

        {/* Global Context Selection (Visible across list/create/edit views) */}
        {view !== 'workspace' && (
          <div>
            <ClassSelector
              batches={batches}
              selectedBatchId={selectedBatchId}
              onBatchChange={handleBatchChange}
              onBatchCreate={handleBatchCreate}
              onBatchDelete={handleBatchDelete}
              getBatchDeletionStatus={getBatchDeletionStatus}
              getSectionDeletionStatus={getSectionDeletionStatus}
              departments={departments}
              years={years}
              semesters={semesters}
              sections={sections}
              selectedDeptId={selectedDeptId}
              selectedYearId={selectedYearId}
              selectedSemId={selectedSemId}
              selectedSectionId={selectedSectionId}
              onDeptChange={handleDeptChange}
              onYearChange={handleYearChange}
              onSemChange={handleSemChange}
              onSectionChange={handleSectionChange}
              onSectionAdd={handleSectionAdd}
              onSectionRemove={handleSectionRemove}
            />
          </div>
        )}

        {view !== 'workspace' && view !== 'course-obe' && (
          <StudentManagement
            sectionId={selectedSectionId}
            semesterId={selectedSemId}
            sectionName={sections.find((section) => section.id === selectedSectionId)?.name}
            batchName={batches.find((batch) => batch.id === selectedBatchId)?.batchName}
            departmentName={departments.find((department) => department.id === selectedDeptId)?.name}
            yearName={years.find((year) => year.id === selectedYearId)?.name}
            students={students}
            loading={studentsLoading}
            onStudentAdded={handleStudentAdded}
          />
        )}

        {/* View Routing */}
        {view === 'list' && (
          <ExamList
            exams={exams}
            subjects={subjects}
            onOpenExam={(examId, subjectId) => void loadExamContext(examId, subjectId, 'workspace')}
            onEditExam={(examId, subjectId) => void loadExamContext(examId, subjectId, 'edit')}
            onDeleteExam={(exam) => void handleDeleteExam(exam)}
            onCreateNew={(subjectId, defaultExamName, defaultExamType) => {
              captureHomeScrollPosition();
              setSelectedSubjectId(subjectId);
              setNewExamName(defaultExamName);
              setNewExamType(defaultExamType);
              setCurrentExam(null);
              setView('create');
            }}
            selectedDeptId={selectedDeptId}
            selectedYearId={selectedYearId}
            selectedSemId={selectedSemId}
            selectedSectionId={selectedSectionId}
            onCreateSubject={handleCreateSubject}
            onRemoveSubject={handleRemoveSubject}
            onRestoreSubject={handleRestoreSubject}
            onPermanentlyDeleteSubject={handlePermanentlyDeleteSubject}
          />
        )}

        {(view === 'create' || view === 'edit') && (
          <ExamForm
            initialExam={view === 'edit' ? currentExam : null}
            initialName={newExamName}
            initialType={newExamType}
            batchId={selectedBatchId}
            departmentId={selectedDeptId}
            yearId={selectedYearId}
            semesterId={selectedSemId}
            sectionId={selectedSectionId}
            subjectId={selectedSubjectId}
            onSaveSuccess={handleSaveSuccess}
            onCancel={handleReturnHome}
          />
        )}

        {view === 'workspace' && currentExam && (
          <ExamWorkspace
            exam={currentExam}
            batchName={batches.find((batch) => batch.id === currentExam.batchId)?.batchName || ''}
            rosterVersion={rosterVersion}
            studentCount={students.length}
            showTargetAttainmentReference={years.some(
              (year) => year.id === currentExam.yearId && year.yearNumber === 3
            )}
            onEditConfig={() => void loadExamContext(currentExam.id, currentExam.subjectId, 'edit')}
            onBackToSelection={handleReturnHome}
          />
        )}

        {view === 'course-obe' && (
          <CourseOBEAnalysis
            key={`${selectedBatchId}:${selectedDeptId}:${selectedYearId}:${selectedSemId}:${selectedSectionId}:${selectedSubjectId}`}
            batchId={selectedBatchId}
            batchName={batches.find((batch) => batch.id === selectedBatchId)?.batchName || ''}
            departmentName={departments.find((department) => department.id === selectedDeptId)?.name || 'Department'}
            departmentId={selectedDeptId}
            yearName={years.find((year) => year.id === selectedYearId)?.name || 'Year'}
            yearId={selectedYearId}
            semesterName={semesters.find((semester) => semester.id === selectedSemId)?.name || 'Semester'}
            semesterId={selectedSemId}
            sectionId={selectedSectionId}
            sectionName={sections.find((section) => section.id === selectedSectionId)?.name || ''}
            subjects={subjects}
            selectedSubjectId={selectedSubjectId}
            onSubjectChange={setSelectedSubjectId}
          />
        )}
      </main>

      <footer className="border-t border-slate-200 bg-white py-3 text-center text-xs text-slate-500">
        Manakula Vinayagar Institute of Technology
      </footer>
    </div>
  );
}
