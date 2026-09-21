import { get, put } from "@vercel/blob";

export const ACTIVE_WINDOW_MS = 10 * 60 * 1000;
export const SESSION_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const RUN_PATTERN = /^FR-\d{8}T\d{12}Z$/;
const SON_PATTERN = /^SON-\d{8}T\d{12}Z$/;

export function statsPath() {
  return process.env.VERCEL_ENV === "preview"
    ? "platform/platform_stats.preview.json"
    : "platform/platform_stats.json";
}

function emptyStats() {
  return { total_users: 0, active_users: 0, total_forecast_runs: 0,
    total_son_recommendations: 0, total_exports: 0, updated_at: null,
    sessions: {}, recorded_forecasts: {}, recorded_son_evaluations: {} };
}

function publicStats(stats, now) {
  return {
    total_users: stats.total_users,
    active_users: Object.values(stats.sessions).filter(lastSeen =>
      typeof lastSeen === "number" && lastSeen > now - ACTIVE_WINDOW_MS && lastSeen <= now).length,
    total_forecast_runs: stats.total_forecast_runs,
    total_son_recommendations: stats.total_son_recommendations,
    total_exports: stats.total_exports,
    updated_at: stats.updated_at,
  };
}

// One read-modify-write queue per function instance. Distributed concurrent
// writers can still race; approximate counters are intentional at this scale.
export function createStatsStore({ read, write, now = Date.now }) {
  let queue = Promise.resolve();
  async function load() {
    const stored = await read();
    if (stored === null) return emptyStats();
    // Fail closed on a corrupt object; never silently reset persistent totals.
    for (const field of ["total_users", "total_forecast_runs", "total_son_recommendations", "total_exports"]) {
      if (!Number.isSafeInteger(stored[field]) || stored[field] < 0) throw new Error("Invalid stats data");
    }
    if (!stored.sessions || typeof stored.sessions !== "object" || Array.isArray(stored.sessions)) throw new Error("Invalid sessions");
    return { ...emptyStats(), ...stored };
  }
  function update(change) {
    const operation = queue.then(async () => {
      const stats = await load();
      const time = now();
      if (change(stats, time) !== false) {
        stats.active_users = publicStats(stats, time).active_users;
        stats.updated_at = new Date(time).toISOString();
        await write(stats);
      }
      return publicStats(stats, time);
    });
    queue = operation.then(() => undefined, () => undefined);
    return operation;
  }
  return {
    async get() { return publicStats(await load(), now()); },
    heartbeat(id) {
      if (!SESSION_PATTERN.test(id)) return Promise.reject(new Error("Invalid anonymous session"));
      const key = id.toLowerCase();
      return update((stats, time) => {
        if (!Object.hasOwn(stats.sessions, key)) stats.total_users++;
        stats.sessions[key] = time;
      });
    },
    forecast(result) {
      if (result?.status !== "completed" || !RUN_PATTERN.test(result?.run_id ?? "")) return Promise.resolve();
      return update(stats => {
        if (Object.hasOwn(stats.recorded_forecasts, result.run_id)) return false;
        stats.recorded_forecasts[result.run_id] = true;
        stats.total_forecast_runs++;
      });
    },
    son(result) {
      if (result?.status !== "completed" || !SON_PATTERN.test(result?.son_id ?? "") || !Array.isArray(result?.recommendations)) return Promise.resolve();
      return update(stats => {
        if (Object.hasOwn(stats.recorded_son_evaluations, result.son_id)) return false;
        stats.recorded_son_evaluations[result.son_id] = true;
        stats.total_son_recommendations += result.recommendations.length;
      });
    },
    export() { return update(stats => { stats.total_exports++; }); },
  };
}

const store = createStatsStore({
  async read() {
    const token = process.env.BLOB_READ_WRITE_TOKEN?.trim();
    if (!token) throw new Error("Platform storage is not configured");
    const result = await get(statsPath(), { access: "private", token, useCache: false, abortSignal: AbortSignal.timeout(5000) });
    if (!result) return null;
    if (result.statusCode !== 200) throw new Error("Platform storage read failed");
    return new Response(result.stream).json();
  },
  async write(stats) {
    const token = process.env.BLOB_READ_WRITE_TOKEN?.trim();
    await put(statsPath(), JSON.stringify(stats), {
      access: "private", token, addRandomSuffix: false, allowOverwrite: true,
      contentType: "application/json", cacheControlMaxAge: 60, abortSignal: AbortSignal.timeout(5000),
    });
  },
});

export const platformStats = store;

export async function safelyRecord(action) {
  try { await action(); }
  catch { console.warn("Platform activity update unavailable."); }
}

// Observe complete messages while forwarding the exact original bytes. Only
// the completed result waits for its counter write; live progress is untouched.
export function observeForecastStream(body, contentType, record = result => store.forecast(result)) {
  const decoder = new TextDecoder();
  let pending = "";
  const sse = contentType.includes("text/event-stream");
  async function consume(text, final = false) {
    pending += text;
    const separator = sse ? /\r?\n\r?\n/ : /\r?\n/;
    let match;
    while ((match = separator.exec(pending)) || (final && pending.length)) {
      const boundary = match ? match.index : pending.length;
      const frame = pending.slice(0, boundary);
      pending = match ? pending.slice(boundary + match[0].length) : "";
      const payload = sse ? frame.split(/\r?\n/).filter(line => line.startsWith("data:")).map(line => line.slice(5).trim()).join("\n") : frame.trim();
      if (!payload) continue;
      let event;
      try { event = JSON.parse(payload); } catch { continue; }
      if (event.type === "result" && event.data?.status === "completed") await safelyRecord(() => record(event.data));
    }
    if (pending.length > 1024 * 1024) pending = "";
  }
  return body.pipeThrough(new TransformStream({
    async transform(chunk, controller) { await consume(decoder.decode(chunk, { stream: true })); controller.enqueue(chunk); },
    async flush() { await consume(decoder.decode(), true); },
  }));
}

// Observe small JSON result responses without cloning/locking the upstream body.
// Original chunks are forwarded; storage failures never replace the result.
export function observeJsonResponse(body, record) {
  const decoder = new TextDecoder();
  let text = "";
  return body.pipeThrough(new TransformStream({
    transform(chunk, controller) {
      text += decoder.decode(chunk, { stream: true });
      controller.enqueue(chunk);
    },
    async flush() {
      text += decoder.decode();
      let result;
      try { result = JSON.parse(text); } catch { return; }
      if (result.status === "completed") await safelyRecord(() => record(result));
    },
  }));
}
