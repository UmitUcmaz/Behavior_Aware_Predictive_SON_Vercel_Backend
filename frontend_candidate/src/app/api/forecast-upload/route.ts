import { handleUpload, type HandleUploadBody } from '@vercel/blob/client';
import { uploadConstraints } from '../../../lib/forecast-upload.mjs';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  const respond = (status: number, error: string) => Response.json({ error }, {
    status, headers: { 'Cache-Control': 'no-store' },
  });
  if (request.headers.get('origin') !== new URL(request.url).origin ||
      request.headers.get('sec-fetch-site') === 'cross-site') {
    return respond(403, 'Cross-origin uploads are not allowed.');
  }
  if (!process.env.BLOB_READ_WRITE_TOKEN) return respond(503, 'Private upload storage is not configured.');
  if (!request.headers.get('content-type')?.includes('application/json')) {
    return respond(415, 'The upload authorization request must be JSON.');
  }
  try {
    const text = await request.text();
    if (text.length > 4096) return respond(413, 'Upload authorization request is too large.');
    const body = JSON.parse(text) as HandleUploadBody;
    // No completion webhook is needed: the browser sends only the completed
    // pathname to inspection. Blob enforces path, type, size, expiry and no overwrite.
    if (body.type !== 'blob.generate-client-token') return respond(400, 'Invalid upload request.');
    const result = await handleUpload({
      body, request,
      onBeforeGenerateToken: async (pathname, clientPayload, multipart) =>
        uploadConstraints(pathname, clientPayload, multipart),
    });
    return Response.json(result, { headers: { 'Cache-Control': 'no-store' } });
  } catch {
    // SDK errors may contain credential-bearing URLs. Never echo or log them.
    return respond(400, 'Could not authorize CSV upload. Check the file type and size, then retry.');
  }
}
