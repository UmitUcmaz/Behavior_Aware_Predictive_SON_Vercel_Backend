import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import { GET, POST } from '../src/app/api/backend/[...path]/route.ts';

const originalFetch = globalThis.fetch;
const originalBase = process.env.BACKEND_API_BASE_URL;
const originalBypass = process.env.BACKEND_PROTECTION_BYPASS;
const base = 'https://frontend.example';
const context = (path) => ({ params: Promise.resolve({ path: path.split('/') }) });
beforeEach(() => {
  process.env.BACKEND_API_BASE_URL = 'https://backend.example/api';
  process.env.BACKEND_PROTECTION_BYPASS = 'test-only-server-secret';
});
afterEach(() => {
  globalThis.fetch = originalFetch;
  for (const [key, value] of [['BACKEND_API_BASE_URL', originalBase], ['BACKEND_PROTECTION_BYPASS', originalBypass]]) {
    if (value === undefined) delete process.env[key]; else process.env[key] = value;
  }
});

test('forwards chart query to fixed backend with server-only credentials', async () => {
  globalThis.fetch = async (url, options) => {
    assert.equal(url.href, 'https://backend.example/api/forecast/FR-20260919T124314912789Z/chart?cell_name=CELL_1&kpi=ACTIVE_USERS');
    assert.equal(options.headers.get('x-vercel-protection-bypass'), 'test-only-server-secret');
    assert.equal(options.headers.get('cookie'), null);
    assert.equal(options.headers.get('authorization'), null);
    assert.equal(options.redirect, 'manual');
    return Response.json({ history: [1], forecast: [2] }, { headers: { 'set-cookie': 'private=1' } });
  };
  const path = 'forecast/FR-20260919T124314912789Z/chart';
  const response = await GET(new Request(`${base}/api/backend/${path}?cell_name=CELL_1&kpi=ACTIVE_USERS`, {
    headers: { cookie: 'frontend=1', authorization: 'browser-value', 'x-vercel-protection-bypass': 'browser-value' },
  }), context(path));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('set-cookie'), null);
  assert.equal(response.headers.get('x-vercel-protection-bypass'), null);
  assert.deepEqual(await response.json(), { history: [1], forecast: [2] });
});

test('streams first SSE chunk before upstream completion, preserving event bytes', async () => {
  let controller;
  globalThis.fetch = async () => new Response(new ReadableStream({ start(c) { controller = c; } }), {
    headers: { 'content-type': 'text/event-stream' },
  });
  const response = await GET(new Request(`${base}/api/backend/dataset-generator/generate/events?cell_count=100`), context('dataset-generator/generate/events'));
  assert.equal(response.headers.get('x-accel-buffering'), 'no');
  const reader = response.body.getReader();
  const chunk = 'data: {"type":"progress","data":{"percent":1}}\n\n';
  controller.enqueue(new TextEncoder().encode(chunk));
  const first = await reader.read();
  assert.equal(new TextDecoder().decode(first.value), chunk);
  assert.equal(first.done, false);
  controller.close();
  assert.equal((await reader.read()).done, true);
});

test('preserves POST multipart body, content type, and upstream error status', async () => {
  const form = new FormData(); form.set('run_id', 'FR-20260919T124314912789Z');
  const request = new Request(`${base}/api/backend/validate`, { method: 'POST', body: form, headers: { origin: base } });
  globalThis.fetch = async (url, options) => {
    assert.equal(options.method, 'POST');
    assert.equal(options.duplex, 'half');
    const forwarded = new Request(url, options);
    assert.equal((await forwarded.formData()).get('run_id'), 'FR-20260919T124314912789Z');
    return Response.json({ detail: 'example validation failure' }, { status: 422 });
  };
  const response = await POST(request, context('validate'));
  assert.equal(response.status, 422);
  assert.deepEqual(await response.json(), { detail: 'example validation failure' });
});

test('rejects cross-origin and cross-site callers without contacting backend', async () => {
  globalThis.fetch = async () => assert.fail('must not fetch');
  for (const headers of [{ origin: 'https://other.example' }, { 'sec-fetch-site': 'cross-site' }]) {
    assert.equal((await GET(new Request(`${base}/api/backend/health`, { headers }), context('health'))).status, 403);
  }
});

test('rejects unlisted endpoints, traversal, and large CSV proxy requests', async () => {
  globalThis.fetch = async () => assert.fail('must not fetch');
  for (const path of ['artifacts', '../health', 'https://other.example', 'forecast/FR-20260919T124314912789Z/csv']) {
    assert.equal((await GET(new Request(`${base}/api/backend/test`), context(path))).status, 404);
  }
});

test('does not follow authentication redirects or expose their location', async () => {
  globalThis.fetch = async () => new Response(null, { status: 307, headers: { location: 'https://auth.example/private' } });
  const response = await GET(new Request(`${base}/api/backend/health`), context('health'));
  assert.equal(response.status, 502);
  assert.equal(response.headers.get('location'), null);
});

test('missing configuration fails closed', async () => {
  delete process.env.BACKEND_PROTECTION_BYPASS;
  globalThis.fetch = async () => assert.fail('must not fetch');
  assert.equal((await GET(new Request(`${base}/api/backend/health`), context('health'))).status, 503);
});

test('sanitizes fetch failures and strips caller bypass query parameters', async () => {
  globalThis.fetch = async (url) => {
    assert.equal(url.searchParams.has('x-vercel-protection-bypass'), false);
    assert.equal(url.searchParams.has('x-vercel-set-bypass-cookie'), false);
    throw new Error('sensitive upstream diagnostic');
  };
  const response = await GET(new Request(`${base}/api/backend/health?x-vercel-protection-bypass=bad&x-vercel-set-bypass-cookie=true`), context('health'));
  assert.equal(response.status, 502);
  assert.equal((await response.text()).includes('sensitive'), false);
});

test('SON JSON observer preserves original bytes and completed result', async()=>{
 const {platformStats}=await import('../src/lib/platform-stats.server.mjs');const original=platformStats.son;let calls=0;
 const text='  '+JSON.stringify({status:'completed',son_id:'SON-20260919T124314912789Z',recommendations:[{}]})+' ';
 platformStats.son=async result=>{calls++;assert.equal(result.recommendations.length,1);};
 globalThis.fetch=async()=>new Response(text,{headers:{'content-type':'application/json'}});
 try{const response=await POST(new Request(base+'/api/backend/son/evaluate',{method:'POST',body:'{}'}),context('son/evaluate'));assert.equal(response.status,200);assert.equal(await response.text(),text);assert.equal(calls,1);}finally{platformStats.son=original;}
});
