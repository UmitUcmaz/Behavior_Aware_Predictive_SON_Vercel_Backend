import { getDownloadUrl, issueSignedToken, presignUrl } from "@vercel/blob";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const id = new URL(request.url).searchParams.get("validation_id")?.trim() ?? "";
  const headers = { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };
  if (!/^VAL-\d{8}T\d{12}Z$/.test(id)) {
    return Response.json({ error: "Invalid validation id." }, { status: 400, headers });
  }
  const token = process.env.BLOB_READ_WRITE_TOKEN?.trim();
  if (!token) {
    return Response.json({ error: "Validation download service is not configured." }, { status: 503, headers });
  }
  try {
    const pathname = `validation-runs/${id}/validation_matched.csv`;
    const now = Date.now();
    const signed = await issueSignedToken({ token, pathname, operations: ["get"], validUntil: now + 600_000 });
    const { presignedUrl } = await presignUrl(signed, {
      pathname, operation: "get", access: "private", validUntil: now + 300_000, useCache: false,
    });
    // CSV bytes travel directly from Blob to the browser, regardless of size.
    return new Response(null, { status: 307, headers: { ...headers, Location: getDownloadUrl(presignedUrl) } });
  } catch {
    return Response.json({ error: "Could not prepare the validation CSV download." }, { status: 502, headers });
  }
}
