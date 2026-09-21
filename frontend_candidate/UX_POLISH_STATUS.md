# Final UX Polish — 2026-09-20

## Deployment
- Production: https://behavior-aware-predictive-son-front.vercel.app
- Deployment: dpl_2pK6iWo8WzBbSChNsPiysiJx1hpL
- Final Preview: https://behavior-aware-predictive-son-frontend-b1bx7cj3y-umitucmaz.vercel.app
- Frontend only deployed. Accepted production backend was not changed or redeployed.
- Preview upstream now uses the accepted production backend through the existing protected same-origin proxy. No model changes.

## Platform Activity
- Private Blob production JSON: platform/platform_stats.json; Preview: platform/platform_stats.preview.json.
- Anonymous UUID v4 persists in browser localStorage. This counts browser profiles, not identified people. No identity or IP is collected by this feature.
- Visible tabs heartbeat every two minutes and on focus; active users have a heartbeat within ten minutes. Active count is derived at read time, so it expires without needing a scheduler.
- Server observers count only completed forecast and SON results. Run IDs deduplicate repeated result delivery. Export counts successful forecast signed-URL creation, not completed downloads.
- Public API exposes only aggregate counters and update time, never session maps or credentials.
- Counters start at this release, including smoke visits/runs; historical placeholder numbers are not migrated as real usage.
- Simple Blob read-modify-write, serialized per function instance. Concurrent distributed writers may lose increments; these are approximate usage counters, not billing records.
- Storage failure does not break forecasting, SON, or downloads. Metrics failure is logged generically; the Home widget shows unavailable when its read fails.
- Platform Blob prefix is outside existing artifact TTL cleanup; cleanup code is unchanged.

## Presentation
- White Platform Activity title and live counts.
- Generated card retains status, cell count, history rows and generation ID. Date Range remains in Dataset Summary.
- Validation status is under configuration. Matching/Accuracy share a 40/60 summary row and stack below 760px. The existing KPI values and signed validation export are inside Accuracy.
- Chart is immediately below the summary, with a 320px desktop plot area. Chart calculations/selection logic remain untouched.

## Verification
- npm run build: PASS locally and on Vercel.
- 21 Node regression tests: PASS. Includes proxy streaming/byte preservation, metrics persistence/deduplication, active window, API payload/origin checks and layout structure.
- Preview and production 100 cells × 96 steps: PASS, 100 successful / 0 failed, 9600 rows.
- Production seed-42 run: FR-20260920T091605467830Z.
- Signature: 7cf7abe00bfa977b; baseline equality PASS.
- Forecast CSV: 874016 bytes; SHA-256 77a7ebf074ed6ace9d5dba62d2bf4710d9c0947d84315b54ac86446c72225923; baseline byte equality PASS.
- Live generation SSE: 108 progress events; live forecast SSE: 104 progress events.
- Generation wall time: 11.55s; forecast wall time: 10.30s.
- Anti-leak: 2026-09-10 16:00:00 < 2026-09-10 16:15:00.
- Validation: 9534 matches, 100 cells, 3 KPI metrics; chart and direct signed Blob validation export PASS.
- SON: ES/MLB/CAP-only result; 7 recommendations.
- Independent private Blob read verified production deltas: forecast +1, SON +7, export +1.
- Browser Home reload retained the same total-users count (2). White heading, live counters, compact generated card and populated desktop validation layout verified.
- Anonymous production /, /forecast, /validation, /son and activity API: HTTP 200.
- Private CSV without signature: HTTP 403. CSV bytes still downloaded directly from Blob.
- 38 deployed source files: no env files, generated CSVs, tests or temporary artifacts.
- Browser bundle scans: no Blob or backend/frontend bypass secret values.
- Backend/model source hashes unchanged; source/network_traffic.csv.gz remains 45580014 bytes.
- No 2000-cell retest, model changes, CSV changes, cleanup changes, commit or push.

## Changed files (frontend_candidate)
- src/app/globals.css
- src/app/layout.tsx
- src/app/page.tsx
- src/app/forecast/page.tsx
- src/app/validation/page.tsx
- src/app/api/backend/[...path]/route.ts
- src/app/api/forecast-download/route.ts
- src/app/api/platform-activity/route.ts (new)
- src/components/PlatformActivity.tsx (new)
- src/lib/platform-stats.server.mjs (new)
- tests/backend-proxy.test.mjs
- tests/platform-activity.test.mjs (new)
- tests/ux-layout.test.mjs (new)
- tests/ux-smoke.mjs (new)
- UX_POLISH_STATUS.md (new; excluded from deployment)

## Repeat tests
Run node --test tests/backend-proxy.test.mjs tests/platform-activity.test.mjs tests/ux-layout.test.mjs tests/validation-download.test.mjs, then npm run build.
The live tests/ux-smoke.mjs requires private environment variables BAPS_FRONTEND_URL, BAPS_FRONTEND_BYPASS, BLOB_READ_WRITE_TOKEN, BAPS_STATS_PATH and BAPS_STAGE. It generates 100 cells with seed 42, runs 96 steps, and increments real usage counters. Run without concurrent SON/forecast/export tests when asserting exact deltas. Reports and downloaded CSVs are written only to the OS temporary directory, never the deployment source.

## Remaining blockers
None. Existing Node module-type and dependency install-script warnings do not affect build or smoke results.
