import { get } from '@vercel/blob';
import assert from 'node:assert/strict';
import { createHash, randomUUID } from 'node:crypto';
import { writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const base = process.env.BAPS_FRONTEND_URL;
const bypass = process.env.BAPS_FRONTEND_BYPASS?.trim();
if (!base || !bypass) throw new Error('Set production smoke environment privately.');
const expectedHeader = 'CELL_NAME,SDATE,UL_PRB_UTILIZATION_FORECAST,DL_PRB_UTILIZATION_FORECAST,ACTIVE_USERS_FORECAST';
const report = {};
async function request(path, options = {}) {
  const headers = new Headers(options.headers);
  headers.set('x-vercel-protection-bypass', bypass);
  const url = `${base}${path}`;
  return fetch(url, { ...options, headers, redirect: 'manual' });
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
  const before=await json('/api/platform-activity');
  const sessionId=randomUUID();
  for (let i=0;i<2;i++) {
    const heartbeat=await request('/api/platform-activity',{method:'POST',headers:{'content-type':'application/json',origin:base},body:JSON.stringify({session_id:sessionId})});
    assert.equal(heartbeat.status,200);const stats=await heartbeat.json();assert.equal(stats.total_users,before.total_users+1);assert.ok(stats.active_users>=1);assert.equal('sessions' in stats,false);
  }
  record('anonymous-session',{status:'PASS',uniqueIncrement:1,repeatedIncrement:0});
  const health = await json('/api/backend/health');
  assert.equal(health.status, 'ok');
  record('backend-health', { status: 'PASS', engine: health.engine });
  const generation = await sse('generation-sse', '/api/backend/dataset-generator/generate/events?cell_count=100&seed=42');
  assert.equal(generation.cell_count, 100);
  assert.ok(Date.parse(generation.history_end) < Date.parse(generation.ground_truth_start));
  record('anti-leak', { status: 'PASS', generationId: generation.generation_id, historyEnd: generation.history_end, groundTruthStart: generation.ground_truth_start });
  const forecast = await sse('forecast-sse', `/api/backend/forecast/generated/events?generation_id=${encodeURIComponent(generation.generation_id)}&horizon_steps=96`);
  assert.equal(forecast.forecast_rows, 9600);
  assert.equal(forecast.successful_cells, 100); assert.equal(forecast.failed_cells, 0);
  assert.equal(forecast.forecast_signature,'7cf7abe00bfa977b');
  const run=forecast.run_id;
  record('forecast-result', {status:'PASS',runId:run,rows:forecast.forecast_rows,successfulCells:forecast.successful_cells,failedCells:forecast.failed_cells,signature:forecast.forecast_signature,runtime:forecast.runtime_seconds});
  for(const path of ['/','/forecast','/validation','/son']) {
    const response=await request(path); assert.equal(response.status,200);
    assert.match(response.headers.get('content-type'),/text\/html/);
    record(path,{status:'PASS',http:response.status});
  }
  assert.equal((await json('/api/backend/health')).status,'ok');
  record('frontend-backend',{status:'PASS'});
  const chartPath=`forecast/${run}/chart?cell_name=${encodeURIComponent(forecast.cells[0])}&kpi=UL_PRB_UTILIZATION&history_points=96`;
  for (const prefix of ['/api/backend/']) {
    const chart=await json(prefix+chartPath);
    assert.equal(chart.history_points,96); assert.equal(chart.forecast_points,96);
  }
  record('chart',{status:'PASS',history:96,forecast:96});
  const signed=await json(`/api/forecast-download?run_id=${run}`);
  assert.equal(signed.status,'ready');
  const direct=await fetch(signed.download_url); assert.equal(direct.status,200);
  const bytes=Buffer.from(await direct.arrayBuffer());
  assert.equal(createHash('sha256').update(bytes).digest('hex'),'77a7ebf074ed6ace9d5dba62d2bf4710d9c0947d84315b54ac86446c72225923');
  const lines=bytes.toString('utf8').trimEnd().split('\n');
  assert.equal(lines[0].trim(),expectedHeader); assert.equal(lines.length-1,9600);
  assert.equal(new Set(lines.slice(1).map(line=>line.split(',')[0])).size,100);
  const unsigned=new URL(signed.download_url);unsigned.search='';
  const unsignedResponse=await fetch(unsigned,{method:'HEAD'});assert.equal(unsignedResponse.status,403);
  await writeFile(join(tmpdir(),`baps-production-${run}.csv`),bytes);
  record('signed-download',{status:'PASS',bytes:bytes.length,rows:9600,cells:100,header:lines[0].trim(),sha256:createHash('sha256').update(bytes).digest('hex'),unsignedHttp:403});
  const form=new FormData();form.set('run_id',run);
  const validated=await request('/api/backend/validate',{method:'POST',body:form,headers:{origin:base}});
  assert.equal(validated.status,200);
  const validation=await validated.json(); assert.equal(validation.status,'completed');
  assert.ok(validation.matched_rows > 0 && validation.matched_rows <= 9600);assert.equal(validation.matched_cells,100);assert.equal(validation.metrics.length,3);
  record('validation',{status:'PASS',validationId:validation.validation_id,matchedRows:validation.matched_rows,matchedCells:validation.matched_cells,metrics:validation.metrics});
  const validationChart=await json(`/api/backend/validation/${validation.validation_id}/chart?cell_name=${encodeURIComponent(forecast.cells[0])}&kpi=ACTIVE_USERS`);
  assert.equal(validationChart.status,'ready'); assert.ok(validationChart.points.length>0 && validationChart.points.length<=96);
  record('validation-chart',{status:'PASS',points:validationChart.points.length});
  const download=await request(`/api/validation-download?validation_id=${validation.validation_id}`);
  assert.equal(download.status,307);
  const validationBlob=await fetch(download.headers.get('location'));assert.equal(validationBlob.status,200);
  const validationBytes=Buffer.from(await validationBlob.arrayBuffer());
  assert.equal(validationBytes.toString('utf8').trimEnd().split('\n').length-1,validation.matched_rows);
  record('validation-download',{status:'PASS',bytes:validationBytes.length,rows:validation.matched_rows});
  const evaluated=await request('/api/backend/son/evaluate',{method:'POST',headers:{'content-type':'application/json',origin:base},body:JSON.stringify({run_id:run,rules:{}})});
  assert.equal(evaluated.status,200);
  const son=await evaluated.json();assert.equal(son.status,'completed');assert.equal(son.forecast_rows,9600);assert.equal(son.total_cells,100);
  assert.ok(son.recommendations.every(r=>['ES','MLB','CAP'].includes(r.recommendation)));
  record('son',{status:'PASS',sonId:son.son_id,summary:son.summary});
  for (const path of ['validation/runs','son/runs']) {
    const response=await request(`/api/backend/${path}`);assert.equal(response.status,200);
  }
  assert.equal((await request('/api/backend/health',{headers:{origin:'https://untrusted.example'}})).status,403);
  assert.equal((await request(`/api/backend/forecast/${run}/csv`)).status,404);
  record('route-security',{status:'PASS'});
  const after=await json('/api/platform-activity');
  assert.equal(after.total_forecast_runs,before.total_forecast_runs+1);
  assert.equal(after.total_son_recommendations,before.total_son_recommendations+son.recommendations.length);
  assert.equal(after.total_exports,before.total_exports+1);
  const stored=await get(process.env.BAPS_STATS_PATH,{access:'private',token:process.env.BLOB_READ_WRITE_TOKEN.trim(),useCache:false});
  assert.equal(stored.statusCode,200);const durable=await new Response(stored.stream).json();
  for(const key of ['total_users','total_forecast_runs','total_son_recommendations','total_exports'])assert.equal(durable[key],after[key]);
  assert.ok(durable.sessions[sessionId]);assert.equal(durable.recorded_forecasts[run],true);assert.equal(durable.recorded_son_evaluations[son.son_id],true);
  record('persistent-activity',{status:'PASS',forecastDelta:1,sonDelta:son.recommendations.length,exportDelta:1,totals:after});
} catch(error) {
  record('failure',{status:'FAIL',message:error.message});process.exitCode=1;
} finally {
  await writeFile(join(tmpdir(),`baps-ux-${process.env.BAPS_STAGE ?? 'preview'}-smoke-report.json`),JSON.stringify(report,null,2));
}
