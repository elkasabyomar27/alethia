# Guided portfolio preparation — 2026-10-27

## Published release

The user confirmed interactive verification and explicitly approved public publication. Production URL: **https://alethia-three.vercel.app**. Deployment `dpl_8FF6MX48XEbNAdEQZS18oruQT9hJ`, project `alethia`, team `omars-projects-39146462`, target `production`.

The Vercel connector denied project creation (403), so the user completed the official CLI sign-in and the same authorized team was targeted through CLI 65.4.0. Only the verified built static artifact was staged under ignored `reports/generated/portfolio-release-20261027/` and deployed, with static project settings and the existing security headers. No backend, environment file, local database, or source repository was uploaded.

Anonymous HTTPS verification returned 200 for the production URL, favicon, entry JavaScript/CSS, four deity images, pilot/setup documents, and two historical screenshots. All checked asset hashes exactly matched the approved local build. The deployed CSP includes `connect-src 'none'`. Agent-driven browser automation remained unavailable; the user's own verification and anonymous HTTP/artifact checks are the evidence for this release. No GitHub commit or push was performed.

The remaining sections record the earlier preparation and its checks; the publication gate has now been approved and completed.

## What is implemented

- A separate React entry selected with `VITE_APP_MODE=local|portfolio`, default local. The explicit `--mode portfolio` profile always selects the portfolio entry. This is resolved at build time, so local API modules are not bundled into the guided build.
- A deeply frozen, typed adapter over `frontend/src/portfolio/demo.json`. Only six exact original fictional documents, four explicitly selected saved examples, and sanitized actual pilot aggregates are included. No review identities, reserved questions, local ticket records, or database files are exported.
- Saved English/MSA/Egyptian Arabic playback and unsupported-question behaviour, exact source-section links, a read-only document filter, illustrative handoff steps, actual pilot/language tables, limitations, architecture/setup notes, and labelled historical local-app screenshots.
- CSP for Vercel includes `connect-src 'none'`. The portfolio preview has no API proxy. No Gemini key or provider invocation is needed.
- Pinned GitHub Actions verify the backend, both frontend modes, public bundle boundaries, and server-rendered route contracts. No repository, commit, push, or remote CI run has been created.

## Run and verify

From `frontend`:

```powershell
npm.cmd run build:portfolio
npm.cmd run preview:portfolio
```

Open http://127.0.0.1:4174. The complete local app continues on port 5173. The generated portfolio output is `frontend/dist-portfolio`; the normal build remains `frontend/dist`.

From the project root, `scripts/verify.ps1` runs dependency checks, backend tests, both builds, the bundle audit, and five server-rendered portfolio route/state contracts. It does not run embedding inference or Gemini. Base-only CI may skip optional ML tests.

To deliberately refresh the public data after checking the local examples and a completed reviewed-development run:

```powershell
.\.venv\Scripts\python.exe scripts\export_portfolio.py COMPLETED_REVIEWED_RUN_ID
```

The exporter verifies that every source document matches the checked-in fictional original and every saved quote resolves to a current source. It fails on missing/changed/private sources rather than publishing a partial export. It contains a fixed allowlist of four saved conversation IDs; these are local source selectors, not public identifiers. Raw frozen snapshots stay under ignored `reports/generated/portfolio-pilot/`.

## Actual pilot

Run `c7b2ad2ed2ef4c4b88eb3135d3d32d55`: 18 frozen reviewed questions, 15 answerable scored, 10 intent groups; all three methods completed 54 queries with unchanged RAM guards. The pre-run snapshot was checked against the report's actual review snapshot. See [pilot summary](pilot-summary.md) for metrics, language coverage, anonymized failures, corpus hash, and single-pass limitations.

## Verification completed

- 222 backend/public-data tests passed; one pre-existing Starlette/AnyIO deprecation warning.
- Both local and guided TypeScript/Vite production builds passed.
- Public-bundle scan passed: no API fetch paths, secret patterns, raw review snapshots, local databases, or model artifacts.
- Actual guided React components rendered successfully for Oracle, Library with a valid citation, Themis with actual metrics, Dispatch, and a missing citation. This is component/server rendering, not an interactive browser test.
- HTTP checks returned 200 for the guided index, entry assets, four public documents, and two labelled historical screenshots; the full local app's API proxy also remained healthy.
- Private Notion hub with milestone board and experiment register created; pilot summary recorded. Drive presentation folder and eight files verified with `shared: false`.

## Deferred verification — user-approved

Browser and Windows computer-use helpers failed before page initialization with a missing runtime-path error. The user chose to finish preparation and verify visuals later. No new guided-build screenshots, interactive playback checks, mobile layout assertions, console/network capture, or stopped-backend browser test is claimed.

Before release, test at 1440×1050 and 390×844: all four examples, playback/replay/complete answer, evidence navigation and reload, invalid source, filename match/no-match, handoff reset, metrics table keyboard scrolling, reduced motion, and no horizontal page overflow. In DevTools, block port 8000 or stop the backend when no review is being edited; all guided flows must still work with zero API requests. Confirm the banner is always clear and capture new screenshots.

## Publication gate

1. Complete the deferred interactive browser checklist and inspect the exact public artifact.
2. Confirm the intended Vercel personal account and project, with eligible free personal/non-commercial use. Configure the project root as `frontend`; `frontend/vercel.json` selects the guided build. No functions, model hosting, Supabase resource, or paid add-on is required.
3. Obtain explicit publication approval. GitHub initialization/commit/push and remote workflow activation require separate explicit approval.
4. Verify the deployed artifact and its CSP, citations, assets, labels, and absence of API requests. No release has been performed in this milestone.
