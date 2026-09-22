import { platformStats, observeJsonResponse, observeForecastStream } from "../../../../lib/platform-stats.server.mjs";
// Keep protected Preview backend credentials on the server. The browser uses
// /api/backend; SSE bodies are passed through without buffering or reformatting.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

const GET_PATHS = [
  /^health$/,
  /^forecast\/uploaded\/events$/,
  /^dataset-generator\/generate\/events$/,
  /^forecast\/generated\/events$/,
  /^forecast\/FR-\d{8}T\d{12}Z\/(chart|status)$/,
  /^(validation|son)\/runs$/,
  /^validation\/[A-Za-z0-9_-]+\/(chart|csv)$/,
];
const POST_PATHS = [
  /^session\/cleanup$/,
  /^forecast\/inspect-blob$/,
  /^dataset-generator\/generate(?:\/stream)?$/,
  /^forecast\/(inspect|start|generated(?:\/stream)?)$/,
  /^validate$/,
  /^validate-blob$/,
  /^son\/evaluate$/,
];

type Context = { params: Promise<{ path: string[] }> };

function error(status: number, message: string) {
  return Response.json({ error: message }, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}

async function forward(request: Request, context: Context) {
  const incoming = new URL(request.url);
  const origin = request.headers.get("origin");
  if ((origin && origin !== incoming.origin) ||
      request.headers.get("sec-fetch-site") === "cross-site") {
    return error(403, "Cross-origin requests are not allowed.");
  }

  const { path } = await context.params;
  const pathname = path.join("/");
  const allowed = request.method === "GET" ? GET_PATHS : POST_PATHS;
  if (!allowed.some((pattern) => pattern.test(pathname))) {
    return error(404, "Backend endpoint not available.");
  }

  const base = process.env.BACKEND_API_BASE_URL;
  const bypass = process.env.BACKEND_PROTECTION_BYPASS?.trim();
  if (!base || !bypass) {
    return error(503, "Preview backend connection is not configured.");
  }

  try {
    const upstream = new URL(base);
    if (upstream.protocol !== "https:" || upstream.username || upstream.password ||
        upstream.pathname.replace(/\/$/, "") !== "/api") {
      return error(503, "Preview backend URL is not configured correctly.");
    }
    upstream.pathname = `/api/${pathname}`;
    upstream.search = incoming.search;
    upstream.searchParams.delete("x-vercel-protection-bypass");
    upstream.searchParams.delete("x-vercel-set-bypass-cookie");
    const headers = new Headers({ "x-vercel-protection-bypass": bypass });
    for (const name of ["accept", "content-type"]) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }

    const options: RequestInit & { duplex?: "half" } = {
      method: request.method,
      headers,
      cache: "no-store",
      redirect: "manual",
      signal: request.signal,
    };
    if (request.method === "POST") {
      options.body = request.body;
      options.duplex = "half";
    }
    const response = await fetch(upstream, options);
    // Never expose upstream authentication redirects to the browser.
    if (response.status >= 300 && response.status < 400) {
      await response.body?.cancel();
      return error(502, "Unexpected backend redirect.");
    }
    const outgoing = new Headers({
      "Cache-Control": "no-store, no-transform",
      "X-Content-Type-Options": "nosniff",
    });
    for (const name of ["content-type", "content-disposition"]) {
      const value = response.headers.get(name);
      if (value) outgoing.set(name, value);
    }
    if (response.headers.get("content-type")?.includes("text/event-stream")) {
      outgoing.set("X-Accel-Buffering", "no");
    }
    let body = response.body;
    if (response.ok) {
      const contentType = response.headers.get("content-type") ?? "";
      if (body && /^forecast\/(generated|uploaded)\/(events|stream)$/.test(pathname)) {
        body = observeForecastStream(body, contentType);
      } else if (contentType.includes("application/json") &&
          (pathname === "son/evaluate" || /^forecast\/(start|generated|FR-\d{8}T\d{12}Z\/status)$/.test(pathname))) {
        if (body) body = observeJsonResponse(body, pathname === "son/evaluate"
          ? (result: unknown) => platformStats.son(result)
          : (result: unknown) => platformStats.forecast(result));
      }
    }
    return new Response(body, { status: response.status, headers: outgoing });
  } catch {
    // Fetch errors can contain URLs and credentials; do not log their payloads.
    return error(502, "Could not reach the Preview backend.");
  }
}

export async function GET(request: Request, context: Context) {
  return forward(request, context);
}

export async function POST(request: Request, context: Context) {
  return forward(request, context);
}
