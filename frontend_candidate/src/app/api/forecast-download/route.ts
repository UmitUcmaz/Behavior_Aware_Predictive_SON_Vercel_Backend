import { platformStats, safelyRecord } from "../../../lib/platform-stats.server.mjs";
import {
  getDownloadUrl,
  issueSignedToken,
  presignUrl,
} from "@vercel/blob";
import {
  NextRequest,
  NextResponse,
} from "next/server";


export const runtime = "nodejs";
export const dynamic = "force-dynamic";


const FORECAST_RUN_ID_PATTERN =
  /^FR-\d{8}T\d{12}Z$/;

const SIGNED_TOKEN_TTL_MS =
  10 * 60 * 1000;

const DOWNLOAD_URL_TTL_MS =
  5 * 60 * 1000;


export async function GET(
  request: NextRequest,
) {
  const runId =
    request.nextUrl.searchParams.get(
      "run_id"
    )?.trim() ?? "";

  if (
    !FORECAST_RUN_ID_PATTERN.test(
      runId
    )
  ) {
    return NextResponse.json(
      {
        status: "error",
        error: "Invalid forecast run id.",
      },
      {
        status: 400,
        headers: {
          "Cache-Control": "no-store",
        },
      }
    );
  }

  const blobToken =
    process.env.BLOB_READ_WRITE_TOKEN?.trim();

  if (!blobToken) {
    return NextResponse.json(
      {
        status: "error",
        error:
          "Forecast download service is not configured.",
      },
      {
        status: 503,
        headers: {
          "Cache-Control": "no-store",
        },
      }
    );
  }

  const pathname =
    `forecast-runs/${runId}/forecast.csv`;

  const now = Date.now();

  const signedTokenValidUntil =
    now + SIGNED_TOKEN_TTL_MS;

  const downloadValidUntil =
    now + DOWNLOAD_URL_TTL_MS;

  try {
    const signedToken =
      await issueSignedToken({
        pathname,
        operations: ["get"],
        validUntil:
          signedTokenValidUntil,
        token: blobToken,
      });

    const {
      presignedUrl,
    } = await presignUrl(
      signedToken,
      {
        pathname,
        operation: "get",
        access: "private",
        validUntil:
          downloadValidUntil,
        useCache: false,
      }
    );

    const downloadUrl =
      getDownloadUrl(
        presignedUrl
      );

    await safelyRecord(() => platformStats.export());

    return NextResponse.json(
      {
        status: "ready",
        run_id: runId,
        pathname,
        download_url:
          downloadUrl,
        expires_at:
          new Date(
            downloadValidUntil
          ).toISOString(),
      },
      {
        headers: {
          "Cache-Control":
            "no-store, max-age=0",
          "X-Content-Type-Options":
            "nosniff",
        },
      }
    );

  } catch {
    console.error(
      "Failed to create forecast signed download URL."
    );

    return NextResponse.json(
      {
        status: "error",
        error:
          "Could not prepare the forecast CSV download.",
      },
      {
        status: 502,
        headers: {
          "Cache-Control": "no-store",
        },
      }
    );
  }
}
