import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { uploadConstraints, validateCsvFile, MAX_UPLOAD_BYTES } from '../src/lib/forecast-upload.mjs';
import { POST } from '../src/app/api/forecast-upload/route.ts';
const path = 'uploads/forecast/12345678-1234-4123-8123-123456789abc/history.csv';
const file = { name: 'input_history.csv', type: 'text/csv', size: 8360245 };
test('large CSV receives narrowly scoped multipart upload constraints', () => {
  const constraints = uploadConstraints(path, JSON.stringify(file), true);
  assert.equal(constraints.maximumSizeInBytes, file.size);
  assert.deepEqual(constraints.allowedContentTypes, ['text/csv']);
  assert.equal(constraints.allowOverwrite, false);
  assert.equal(constraints.addRandomSuffix, false);
  assert.ok(constraints.validUntil > Date.now());
  assert.ok(constraints.validUntil <= Date.now() + 15 * 60 * 1000);
});
test('rejects paths outside upload namespace, traversal, bad MIME, empty and oversize files', () => {
  for (const bad of ['source/network_traffic.csv.gz', 'forecast-runs/run/forecast.csv', path.replace('history.csv', '../history.csv'), 'https://example.com/a.csv']) {
    assert.throws(() => uploadConstraints(bad, JSON.stringify(file), true));
  }
  assert.throws(() => uploadConstraints(path, JSON.stringify(file), false));
  for (const patch of [{ name: 'a.exe' }, { name: '../a.csv' }, { type: 'text/html' }, { size: 0 }, { size: MAX_UPLOAD_BYTES + 1 }]) {
    assert.throws(() => validateCsvFile({ ...file, ...patch }));
  }
  for (const type of ['', 'application/vnd.ms-excel', 'text/csv']) validateCsvFile({ ...file, type });
});
test('token route rejects cross-origin access before issuing tokens', async () => {
  const response = await POST(new Request('https://app.example/api/forecast-upload', {
    method: 'POST', headers: { origin: 'https://attacker.example', 'content-type': 'application/json' }, body: '{}',
  }));
  assert.equal(response.status, 403);
});
test('missing storage credential fails closed', async () => {
  const previous = process.env.BLOB_READ_WRITE_TOKEN;
  delete process.env.BLOB_READ_WRITE_TOKEN;
  try {
    const response = await POST(new Request('https://app.example/api/forecast-upload', {
      method: 'POST', headers: { origin: 'https://app.example', 'content-type': 'application/json' }, body: '{}',
    }));
    assert.equal(response.status, 503);
  } finally { if (previous !== undefined) process.env.BLOB_READ_WRITE_TOKEN = previous; }
});
test('browser sends file only through private Blob upload; generated SSE remains available', () => {
  const page = readFileSync(new URL('../src/app/forecast/page.tsx', import.meta.url), 'utf8');
  assert.match(page, /upload\(pathname, file/);
  assert.match(page, /access: "private", multipart: true/);
  assert.doesNotMatch(page, /new FormData|BLOB_READ_WRITE_TOKEN/);
  assert.match(page, /forecast\/generated\/events/);
  assert.match(page, /forecast\/uploaded\/events/);
  assert.match(page, /forecast\/inspect-blob/);
});
