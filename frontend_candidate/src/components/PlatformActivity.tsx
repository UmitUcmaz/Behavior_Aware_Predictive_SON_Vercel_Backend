"use client";
import { useEffect, useState } from "react";
const SESSION_KEY = "baps_anonymous_session_id";
const EVENT = "baps:platform-stats";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
let memorySession: string | undefined;
type Stats = { total_users: number; active_users: number; total_forecast_runs: number; total_son_recommendations: number; total_exports: number };
export function PlatformSessionHeartbeat() {
  useEffect(() => {
    let id = memorySession;
    try { id = localStorage.getItem(SESSION_KEY) ?? id; } catch { /* Private browsing fallback. */ }
    if (!id || !UUID.test(id)) id = crypto.randomUUID();
    memorySession = id;
    try { localStorage.setItem(SESSION_KEY, id); } catch { /* Keep the anonymous ID in memory. */ }
    const controller = new AbortController();
    let pending = false;
    async function heartbeat() {
      if (document.visibilityState === "hidden" || pending) return;
      pending = true;
      try {
        const response = await fetch("/api/platform-activity", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: id }), signal: controller.signal });
        if (response.ok) window.dispatchEvent(new CustomEvent(EVENT, { detail: await response.json() }));
      } catch { /* Metrics must never interrupt the workflow. */ }
      finally { pending = false; }
    }
    void heartbeat();
    const timer = window.setInterval(heartbeat, 120000);
    document.addEventListener("visibilitychange", heartbeat);
    window.addEventListener("focus", heartbeat);
    return () => { controller.abort(); clearInterval(timer); document.removeEventListener("visibilitychange", heartbeat); window.removeEventListener("focus", heartbeat); };
  }, []);
  return null;
}
export default function PlatformActivity() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    async function refresh() {
      if (document.visibilityState === "hidden") return;
      try {
        const response = await fetch("/api/platform-activity", { cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error("Unavailable");
        setStats(await response.json()); setUnavailable(false);
      } catch { if (!controller.signal.aborted) setUnavailable(true); }
    }
    const receive = (event: Event) => { setStats((event as CustomEvent<Stats>).detail); setUnavailable(false); };
    window.addEventListener(EVENT, receive);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    void refresh(); const timer = window.setInterval(refresh, 60000);
    return () => { controller.abort(); clearInterval(timer); window.removeEventListener(EVENT, receive); window.removeEventListener("focus", refresh); document.removeEventListener("visibilitychange", refresh); };
  }, []);
  const metrics: [keyof Stats, string][] = [["total_users", "Total Users"], ["active_users", "Active Users"], ["total_forecast_runs", "Total Forecast Runs"], ["total_son_recommendations", "Total SON Recommendations"], ["total_exports", "Total Export"]];
  return <aside className="v6-site-metrics" aria-label="Platform activity">
    <div className="v6-site-metrics-head"><div><span>PLATFORM ACTIVITY</span></div><small role="status">{unavailable ? "Unavailable" : stats ? "Live activity" : "Loading…"}</small></div>
    <div className="v6-site-metrics-grid">{metrics.map(([key, label]) => <div key={key}><span>{label}</span><strong>{stats ? stats[key].toLocaleString() : "—"}</strong></div>)}</div>
  </aside>;
}
