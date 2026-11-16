import assert from 'node:assert/strict';
import { test } from 'node:test';
import { buildStudentImportFormData } from './studentImportForm';

test('student upload form includes the selected File object and section ID', () => {
  const file = new File(
    [new Uint8Array([80, 75, 3, 4])],
    'CSE NAMELIST.xlsx',
    { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
  );

  const previewForm = buildStudentImportFormData(1, file);
  assert.equal(previewForm.get('section_id'), '1');
  assert.strictEqual(previewForm.get('file'), file);
  assert.equal((previewForm.get('file') as File).name, file.name);
  assert.equal((previewForm.get('file') as File).type, file.type);
  assert.equal((previewForm.get('file') as File).size, file.size);
  assert.equal(previewForm.has('confirm'), false);

  const importForm = buildStudentImportFormData(1, file, true);
  assert.strictEqual(importForm.get('file'), file);
  assert.equal(importForm.get('section_id'), '1');
  assert.equal(importForm.get('confirm'), 'true');
});