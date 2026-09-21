import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const base = process.env.BAPS_PREVIEW_URL;
const bypass = process.env.BAPS_PREVIEW_BYPASS?.trim();
if (!base || !bypass) throw new Error('Set BAPS_PREVIEW_URL and BAPS_PREVIEW_BYPASS privately.');
const run = 'FR-20260919T124314912789Z';
const expectedHeader = 'CELL_NAME,SDATE,UL_PRB_UTILIZATION_FORECAST,DL_PRB_UTILIZATION_FORECAST,ACTIVE_USERS_FORECAST';
const report = {};
async function request(path, options = {}) {
  const headers = new Headers(options.headers);
  headers.set('x-vercel-protection-bypass', bypass);
  return fetch(`${base}${path}`, { ...options, headers, redirect: 'manual' });
}
function record(name, details) {
  report[name] = details;
  console.log(JSON.stringify({ test: name, ...details }));
}
async function json(path) {
  const response = await request(path);
  if (!response.ok) throw new Error(`Endpoint ${path.split('?')[0]} HTTP ${response.status}`);
  return response.json();
}
async function sse(name, path) {
  const start = performance.now();
  const response = await request(path);
  assert.equal(response.status, 200);
  assert.match(response.headers.get('content-type'), /text\/event-stream/);
  const decoder = new TextDecoder();
  let buffer = '', result, firstProgressMs, resultMs, progressEvents = 0, chunks = 0;
  for await (const chunk of response.body) {
    chunks++;
    buffer += decoder.decode(chunk, { stream: true });
    let boundary;
    while ((boundary = buffer.indexOf('\n\n')) >= 0) {
      const message = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
      for (const line of message.split('\n')) {
        if (!line.startsWith('data:')) continue;
        const event = JSON.parse(line.slice(5).trim());
        if (event.type === 'error') throw new Error(`${name} returned an error event (details withheld)`);
        if (event.type === 'progress') { firstProgressMs ??= performance.now() - start; progressEvents++; }
        if (event.type === 'result') { result = event.data; resultMs = performance.now() - start; }
      }
    }
  }
  assert.ok(result, `${name} missing result`);
  assert.ok(progressEvents > 0 && firstProgressMs < resultMs, `${name} not live`);
  record(name, { status: 'PASS', chunks, progressEvents, firstProgressMs: Math.round(firstProgressMs), totalMs: Math.round(performance.now() - start) });
  return result;
}
try {
  for (const path of ['/', '/forecast']) {
    const response = await request(path);
    assert.equal(response.status, 200);
    assert.match(response.headers.get('content-type'), /text\/html/);
    const html = await response.text();
    assert.ok(html.includes('Forecast'));
    record(path, { status: 'PASS', http: response.status });
  }
  const health = await json('/api/backend/health');
  assert.equal(health.status, 'ok');
  record('backend-health', { status: 'PASS', engine: health.engine });
  assert.equal((await request('/api/backend/health', { headers: { origin: 'https://untrusted.example' } })).status, 403);
  assert.equal((await request('/api/backend/artifacts')).status, 404);
  assert.equal((await request('/api/forecast-download?run_id=invalid')).status, 400);
  record('route-guards', { status: 'PASS' });
  const signed = await json(`/api/forecast-download?run_id=${run}`);
  assert.equal(signed.status, 'ready');
  const direct = await fetch(signed.download_url);
  assert.equal(direct.status, 200);
  const bytes = Buffer.from(await direct.arrayBuffer());
  assert.equal(bytes.length, 17490225);
  const lines = bytes.toString('utf8').trimEnd().split('\n');
  assert.equal(lines[0].trim(), expectedHeader);
  assert.equal(lines.length - 1, 192000);
  const cells = new Set(lines.slice(1).map(line => line.split(',')[0]));
  assert.equal(cells.size, 2000);
  const unsigned = new URL(signed.download_url); unsigned.search = '';
  const privateCheck = await fetch(unsigned, { method: 'HEAD' });
  assert.ok([401, 403, 404].includes(privateCheck.status));
  await writeFile(join(tmpdir(), `baps-${run}.csv`), bytes);
  record('signed-direct-blob-download', { status: 'PASS', http: direct.status, bytes: bytes.length, rows: lines.length - 1, cells: cells.size, header: lines[0].trim(), sha256: createHash('sha256').update(bytes).digest('hex'), unsignedHttp: privateCheck.status });
  const chart = await json(`/api/backend/forecast/${run}/chart?cell_name=CELL_000c7bfe93&kpi=UL_PRB_UTILIZATION&history_points=96`);
  assert.equal(chart.history_points, 96); assert.equal(chart.forecast_points, 96);
  record('existing-2000-run-chart', { status: 'PASS', history: chart.history_points, forecast: chart.forecast_points });
  const generation = await sse('generation-sse', '/api/backend/dataset-generator/generate/events?cell_count=100&seed=42');
  assert.equal(generation.cell_count, 100);
  assert.ok(Date.parse(generation.history_end) < Date.parse(generation.ground_truth_start));
  record('anti-leak', { status: 'PASS', historyEnd: generation.history_end, groundTruthStart: generation.ground_truth_start });
  const forecast = await sse('forecast-sse', `/api/backend/forecast/generated/events?generation_id=${encodeURIComponent(generation.generation_id)}&horizon_steps=96`);
  assert.equal(forecast.forecast_rows, 9600);
  assert.equal(forecast.successful_cells, 100); assert.equal(forecast.failed_cells, 0);
  record('forecast-result', { status: 'PASS', runId: forecast.run_id, rows: forecast.forecast_rows, successfulCells: forecast.successful_cells, failedCells: forecast.failed_cells });
} catch (error) {
  // Assertions compare only public status/count fields, never URLs or tokens.
  record('failure', { status: 'FAIL', message: error.message });
  process.exitCode = 1;
} finally {
  await writeFile(join(tmpdir(), 'baps-preview-smoke-report.json'), JSON.stringify(report, null, 2));
}
