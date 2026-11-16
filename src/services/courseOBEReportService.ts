import { apiUrl } from '../config';

export type CourseOBEReportFormat = 'excel' | 'pdf';

async function downloadCourseOBEReport(
  subjectId: number,
  sectionId: number,
  format: CourseOBEReportFormat,
): Promise<void> {
  const params = new URLSearchParams({ section_id: String(sectionId) });
  const response = await fetch(apiUrl(`/api/course-obe/subjects/${subjectId}/report/${format}?${params.toString()}`));
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Unable to generate ${format.toUpperCase()} report (${response.status}).`);
  }

  const blob = await response.blob();
  if (blob.size === 0) {
    throw new Error(`The ${format.toUpperCase()} report was empty.`);
  }

  const extension = format === 'excel' ? 'xlsx' : 'pdf';
  const disposition = response.headers.get('Content-Disposition') || '';
  const filename = disposition.match(/filename="?([^";]+)"?/)?.[1]
    || `Course_OBE_${subjectId}.${extension}`;
  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(objectUrl);
}

export function downloadCourseOBEExcelReport(subjectId: number, sectionId: number): Promise<void> {
  return downloadCourseOBEReport(subjectId, sectionId, 'excel');
}

export function downloadCourseOBEPdfReport(subjectId: number, sectionId: number): Promise<void> {
  return downloadCourseOBEReport(subjectId, sectionId, 'pdf');
}