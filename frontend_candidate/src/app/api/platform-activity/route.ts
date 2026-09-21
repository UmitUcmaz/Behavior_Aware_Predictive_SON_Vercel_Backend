import { platformStats, SESSION_PATTERN } from "../../../lib/platform-stats.server.mjs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };

export async function GET() {
  try { return Response.json(await platformStats.get(), { headers }); }
  catch { return Response.json({ error: "Platform activity is temporarily unavailable." }, { status: 503, headers }); }
}

export async function POST(request: Request) {
  const origin = request.headers.get("origin");
  if ((origin && origin !== new URL(request.url).origin) || request.headers.get("sec-fetch-site") === "cross-site") {
    return Response.json({ error: "Cross-origin requests are not allowed." }, { status: 403, headers });
  }
  if (!request.headers.get("content-type")?.startsWith("application/json")) {
    return Response.json({ error: "JSON required." }, { status: 415, headers });
  }
  let sessionId;
  try {
    const text = await request.text();
    if (text.length > 256) throw new Error();
    const body = JSON.parse(text);
    if (Object.keys(body).length !== 1 || typeof body.session_id !== "string" || !SESSION_PATTERN.test(body.session_id)) throw new Error();
    sessionId = body.session_id;
  } catch {
    return Response.json({ error: "A valid anonymous session_id is required." }, { status: 400, headers });
  }
  try { return Response.json(await platformStats.heartbeat(sessionId), { headers }); }
  catch { return Response.json({ error: "Platform activity is temporarily unavailable." }, { status: 503, headers }); }
}
