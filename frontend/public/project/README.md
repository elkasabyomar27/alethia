# ALETHIA — local setup

This personal-project showcase plays saved fictional examples. It makes no AI or backend requests. The source repository has not yet been published; these commands are for an existing ALETHIA source checkout.

## Full local application

Requirements: Windows, Python 3.11, Node.js 24. From the checkout root:

    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r backend\requirements-lock.txt
    .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

In another terminal, from frontend:

    npm.cmd ci
    npm.cmd run dev

Open http://127.0.0.1:5173. Configure provider credentials privately using the source checkout's .env.example. Never add them to frontend code. Gemini generation requires internet; optional local semantic search requires the pinned model/runtime and at least 1 GiB available RAM. The source README documents model preparation and all ingestion limits.

## Guided portfolio

From frontend:

    npm.cmd run build:portfolio
    npm.cmd run preview:portfolio

Open http://127.0.0.1:4174. This build needs no backend, model, database, or provider key. It bundles six fictional documents, four saved examples, and sanitized actual pilot aggregates.

## Evidence

Read the [pilot summary](pilot-summary.md), [case study](portfolio-case-study.md), and [walkthrough](demo-walkthrough.md). The pilot is a selected development subset, not a final held-out or generation-quality evaluation. Screenshots are historical captures of the full local app, not live inference in this guided showcase.