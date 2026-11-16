export function buildStudentImportFormData(sectionId: number, file: File, confirm = false, semesterId?: number): FormData {
  const formData = new FormData();
  formData.append('section_id', String(sectionId));
  if (semesterId !== undefined) {
    formData.append('semester_id', String(semesterId));
  }
  if (confirm) {
    formData.append('confirm', 'true');
  }
  formData.append('file', file);
  return formData;
}