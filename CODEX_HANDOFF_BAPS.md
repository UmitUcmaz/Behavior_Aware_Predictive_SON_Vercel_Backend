# Behavior_Aware_Predictive_SON — Codex Handoff

## Working directory
`.`

Frontend:
`frontend_candidate`

## User preference
Do the work directly in the repo. Avoid asking the user to copy/paste repeated commands unless unavoidable.
For source changes, preserve full files and existing behavior. Do not expose secrets.

## Current architecture
- Backend: FastAPI on Vercel
- Frontend: Next.js 16.3.4 / React 19
- Storage: Vercel Blob, private
- Forecast engine: `BASELINE-01`
- Forecast KPIs:
  - `UL_PRB_UTILIZATION`
  - `DL_PRB_UTILIZATION`
  - `ACTIVE_USERS`
- Forecast CSV columns must remain:
  - `CELL_NAME`
  - `SDATE`
  - `UL_PRB_UTILIZATION_FORECAST`
  - `DL_PRB_UTILIZATION_FORECAST`
  - `ACTIVE_USERS_FORECAST`

## Backend Vercel project
Project:
`behavior-aware-predictive-son-vercel-backend`

Project id:
`prj_ZzvvmidHPORMQW4aT0xHazQnwHjr`

Preview deployment used in testing:
`https://behavior-aware-predictive-son-vercel-backend-fn3fly0fx.vercel.app`

Backend Preview tests already PASS:
- `/api/health`
- 100-cell generated dataset SSE
- 100 × 96 forecast SSE
- small forecast CSV export (~874 KB)
- 2000-cell generated dataset
- 2000 × 96 forecast
- 2000-run chart endpoint

Important successful 2K generation:
`GEN-20260919T124131294107Z`

Important successful 2K forecast:
`FR-20260919T124314912789Z`

2K forecast artifact:
`forecast-runs/FR-20260919T124314912789Z/forecast.csv`

2K forecast CSV size:
`17,490,225 bytes`

2K forecast result:
- total_cells: 2000
- successful_cells: 2000
- failed_cells: 0
- forecast_rows: 192000
- forecast_engine: ~23.74s
- total: ~28.70s

Chart test PASS for:
- cell: `CELL_000c7bfe93`
- KPI: `UL_PRB_UTILIZATION`
- history_points: 96
- forecast_points: 96

## Blob safety
Private Blob is used.

Critical permanent source:
`source/network_traffic.csv.gz`

NEVER delete anything under `source/`.

Working artifacts:
- `generations/{GEN-ID}/...`
- `forecast-runs/{FR-ID}/...`
- `validation-runs/...`
- `son-runs/...`

There is cleanup logic for working artifacts / TTL. Preserve it.

## Why signed download was introduced
The 2K forecast CSV is ~17.5 MB.
Do not proxy large forecast CSV bytes through the FastAPI/Vercel Function response.
The intended design is:
browser -> frontend server creates short-lived signed private Blob GET URL -> browser downloads Blob directly.

## Frontend project
Directory:
`frontend_candidate`

Vercel project:
`behavior-aware-predictive-son-frontend`

Project id:
`prj_OrT10E0UmFueKDfwadwIeicx67fH`

`.vercel/project.json` currently points to the correct frontend project.

Frontend Preview env names already configured:
- `NEXT_PUBLIC_API_BASE_URL`
- `BLOB_READ_WRITE_TOKEN`

Do not print or reveal `BLOB_READ_WRITE_TOKEN`.

`NEXT_PUBLIC_API_BASE_URL` should point to:
`https://behavior-aware-predictive-son-vercel-backend-fn3fly0fx.vercel.app/api`

## Frontend build state
`npm run build` currently PASSES locally.

Expected route summary includes:
- static `/`
- static `/forecast`
- static `/validation`
- static `/son`
- static `/about`
- dynamic `/api/forecast-download`

`next.config.ts` was changed from static export to normal Next.js server mode.
Current desired shape:
```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
};

export default nextConfig;
```

`@vercel/blob` was added to frontend dependencies.

A signed-download route exists at:
`frontend_candidate/src/app/api/forecast-download/route.ts`

The forecast page was changed so `Export Forecast CSV` requests the signed-download route and then lets the browser download directly from Blob.

## Current blocker
Frontend deployment builds successfully, but the generated Preview deployment URL currently returns a Vercel-level 404 even for `/`.

Preview deployment:
`https://behavior-aware-predictive-son-frontend-ntlr09n7d-umitucmaz.vercel.app`

Observed:
`vercel curl -i <preview-url>/`
returns:
- HTTP 404
- `X-Vercel-Error: NOT_FOUND`
- body: `The page could not be found / NOT_FOUND`

Likewise:
`/api/forecast-download?run_id=FR-20260919T124314912789Z`
returns the same Vercel-level 404.

This means the request is not reaching the Next.js route handler yet. Diagnose deployment/project/routing first, not signed-token code first.

First frontend deployment was automatically treated as Production because it was the new project's first deployment.
Production alias created:
`https://behavior-aware-predictive-son-front.vercel.app`

Second deployment was reported as Preview and Ready, but its deployment URL gives the Vercel-level 404 above.

## Codex task
Work autonomously in the local repo and get the frontend deployment to a verified end-to-end state.

### Phase 1 — Diagnose frontend Vercel 404
Inspect, do not guess:
- `frontend_candidate/.vercel/project.json`
- `frontend_candidate/next.config.ts`
- `frontend_candidate/package.json`
- `.vercelignore` files that could affect frontend
- Vercel project settings / root-directory assumptions exposed by CLI
- `vercel inspect` for the failing Preview deployment
- deployment file/output metadata if available
- framework detection and build output
- aliases/deployment URL state

Use Vercel CLI directly where useful.
Do not ask the user to retype commands that you can execute.

Fix the actual cause and create a fresh Preview deployment.
Verify `/` returns 200.

### Phase 2 — Verify signed-download API
Once frontend `/` is reachable:
test:
`/api/forecast-download?run_id=FR-20260919T124314912789Z`

Expected response:
- JSON
- status ready/success
- correct pathname
- a non-empty short-lived download URL
- no token leakage in logs/user-visible output

If the signed Blob implementation is wrong, fix it against the actually installed `@vercel/blob` API/types rather than inventing SDK methods.

### Phase 3 — Verify large direct download
Use the signed URL without printing it to the user.
Download the 2K forecast CSV directly from Blob to a temporary/local test file.
Verify size is approximately:
`17,490,225 bytes`

Confirm the file is valid CSV and has expected header:
`CELL_NAME,SDATE,UL_PRB_UTILIZATION_FORECAST,DL_PRB_UTILIZATION_FORECAST,ACTIVE_USERS_FORECAST`

### Phase 4 — Browser/frontend integration
Verify the deployed `/forecast` page:
- loads
- uses backend API base correctly
- backend health/forecast calls are reachable
- Export Forecast CSV uses the signed-download path
- existing generation SSE remains intact
- existing forecast SSE remains intact
- chart remains intact
- do not regress Upload Dataset behavior

### Phase 5 — Deployment protection / CORS
Backend Preview currently has Vercel Deployment Protection.
CLI-authenticated requests work.

For browser frontend -> backend calls, diagnose whether Deployment Protection blocks cross-project browser access.
Use the least invasive secure solution appropriate for Preview testing.
Do not disable security broadly without need.
If a bypass/header/config is required, implement it server-side or through a frontend proxy where appropriate, without exposing secrets to the browser.

Also verify CORS behavior if frontend and backend remain separate origins.

### Phase 6 — Final report
Return a compact report:
- root cause of the 404
- files changed
- fresh frontend Preview URL
- `/` PASS/FAIL
- `/forecast` PASS/FAIL
- signed-download API PASS/FAIL
- 17.49 MB direct CSV PASS/FAIL
- backend browser connectivity PASS/FAIL
- any remaining blocker

## Guardrails
- Do not modify forecast model behavior.
- Do not change forecast output columns.
- Do not delete `source/network_traffic.csv.gz`.
- Preserve Blob cleanup behavior.
- Preserve generation/forecast SSE live progress.
- Preserve current UI unless a change is technically required.
- Do not expose environment secret values.
- Prefer small, explainable changes.
- Run `npm run build` before deploying.
- Do not deploy backend production unless explicitly necessary.
- Frontend Preview is the target until end-to-end verification is complete.
