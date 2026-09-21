import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createStatsStore, observeForecastStream, platformStats, ACTIVE_WINDOW_MS, statsPath } from '../src/lib/platform-stats.server.mjs';
import { GET, POST } from '../src/app/api/platform-activity/route.ts';
const id = '550e8400-e29b-41d4-a716-446655440000';
const run = 'FR-20260919T124314912789Z';
const son = 'SON-20260919T124314912789Z';
function fixture() { let data=null, time=1000000, writes=0; const store=createStatsStore({ read: async()=>structuredClone(data), write:async value=>{ data=structuredClone(value);writes++; },now:()=>time }); return {store,get data(){return data;},get writes(){return writes;},advance:ms=>{time+=ms;}}; }
test('anonymous visitor counted once; heartbeat active window expires and revives',async()=>{
 const f=fixture();assert.equal((await f.store.get()).total_users,0);
 assert.equal((await f.store.heartbeat(id)).total_users,1);
 assert.equal((await f.store.heartbeat(id.toUpperCase())).total_users,1);
 assert.equal((await f.store.get()).active_users,1);f.advance(ACTIVE_WINDOW_MS);
 assert.equal((await f.store.get()).active_users,0);assert.equal((await f.store.heartbeat(id)).active_users,1);
 assert.equal(f.data.total_users,1);assert.ok(f.data.updated_at);assert.equal('sessions' in await f.store.get(),false);
});
test('completed forecasts and SON evaluations are counted once; exports count each success',async()=>{
 const f=fixture();await f.store.forecast({run_id:run,status:'failed'});assert.equal(f.writes,0);
 await f.store.forecast({run_id:run,status:'completed'});await f.store.forecast({run_id:run,status:'completed'});
 await f.store.son({son_id:son,status:'completed',recommendations:[{}, {}, {}]});await f.store.son({son_id:son,status:'completed',recommendations:[{}, {}, {}]});
 await Promise.all([f.store.export(),f.store.export()]);const stats=await f.store.get();
 assert.equal(stats.total_forecast_runs,1);assert.equal(stats.total_son_recommendations,3);assert.equal(stats.total_exports,2);
 const reloaded=createStatsStore({read:async()=>structuredClone(f.data),write:async()=>{}});assert.equal((await reloaded.get()).total_exports,2);
});
test('malformed persistent JSON fails closed without resetting totals',async()=>{
 let writes=0;const s=createStatsStore({read:async()=>({total_users:-1}),write:async()=>{writes++;}});
 await assert.rejects(s.heartbeat(id));assert.equal(writes,0);
});
test('SSE and NDJSON remain byte-identical across split UTF-8 and CRLF frames',async()=>{
 for(const sse of [true,false]) {let calls=0;const messages=[{type:'progress',data:{label:'İlerleme'}},{type:'result',data:{status:'completed',run_id:run}}];
 const text=messages.map(x=>(sse?'data: ':'')+JSON.stringify(x)+(sse?'\r\n\r\n':'\n')).join('');const bytes=new TextEncoder().encode(text);
 const input=new ReadableStream({start(c){for(let i=0;i<bytes.length;i+=7)c.enqueue(bytes.slice(i,i+7));c.close();}});
 const output=observeForecastStream(input,sse?'text/event-stream':'application/x-ndjson',async result=>{calls++;assert.equal(result.run_id,run);});
 assert.deepEqual(new Uint8Array(await new Response(output).arrayBuffer()),bytes);assert.equal(calls,1);
 }
});
test('metric failure preserves completed forecast bytes',async()=>{
 const bytes=new TextEncoder().encode('data: '+JSON.stringify({type:'result',data:{status:'completed',run_id:run}})+'\n\n');
 const stream=new ReadableStream({start(c){c.enqueue(bytes);c.close();}});
 assert.deepEqual(new Uint8Array(await new Response(observeForecastStream(stream,'text/event-stream',async()=>{throw Error('storage offline');})).arrayBuffer()),bytes);
});
test('public API rejects cross-origin and browser counter injection; accepts UUID heartbeat',async()=>{
 const original=platformStats.heartbeat;const originalGet=platformStats.get;const f=fixture();platformStats.heartbeat=f.store.heartbeat;platformStats.get=f.store.get;
 const req=(body,extra={})=>new Request('https://app.example/api/platform-activity',{method:'POST',headers:{'content-type':'application/json',...extra},body:JSON.stringify(body)});
 try {assert.equal((await POST(req({session_id:id},{origin:'https://evil.example'}))).status,403);
 assert.equal((await POST(req({session_id:id,total_forecast_runs:100}))).status,400);
 assert.equal((await POST(req({session_id:'invalid'}))).status,400);
 for(let i=0;i<2;i++){const response=await POST(req({session_id:id}));assert.equal(response.status,200);assert.equal((await response.json()).total_users,1);}
 const response=await GET();assert.equal(response.headers.get('cache-control'),'no-store');const data=await response.json();assert.equal(data.active_users,1);assert.equal('sessions' in data,false);
 platformStats.get=async()=>{throw Error('private info');};const error=await GET();assert.equal(error.status,503);assert.equal((await error.text()).includes('private info'),false);
 }finally{platformStats.heartbeat=original;platformStats.get=originalGet;}
});
test('Preview metrics are isolated from production counters',()=>{const original=process.env.VERCEL_ENV;try{process.env.VERCEL_ENV='preview';assert.equal(statsPath(),'platform/platform_stats.preview.json');process.env.VERCEL_ENV='production';assert.equal(statsPath(),'platform/platform_stats.json');}finally{if(original===undefined)delete process.env.VERCEL_ENV;else process.env.VERCEL_ENV=original;}});
