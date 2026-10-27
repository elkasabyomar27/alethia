# GitHub release preparation

Suggested repository name: `alethia`.

Suggested description: **English/Arabic RAG customer support with hybrid retrieval, traceable sources, local handoff, reproducible evaluation, and a Greek mythology interface.**

Website: https://alethia-three.vercel.app

Suggested topics: `rag`, `retrieval-augmented-generation`, `arabic-nlp`, `fastapi`, `react`, `typescript`, `semantic-search`, `portfolio`.

## Publication boundary

The public source includes the complete application, six fictional bilingual documents, 120 development candidate questions, curated saved examples, sanitized pilot results, artwork credits, setup instructions and CI. The guided website is saved playback; the full application runs locally and uses a backend-only Gemini key or explicitly selected Ollama mode.

Ignored files include `.env`, private Notion/Drive tracking links, 30 reserved questions, review attestations, databases, uploaded documents, indexes, model weights, generated reports, build output and Vercel account linkage. Never use `git add -f` to bypass these exclusions. The candidate scan checks common secret patterns and private links; it is not a guarantee that arbitrary private content is detectable.

The private/public split keeps individual question records and IDs unchanged, preserving per-question review identities. The combined pack order changes because the private holdout is appended, so its pack fingerprint differs from the historical pilot. Saved pilot reports and their original fingerprints are retained unchanged; no new experiment or quality result is implied.

## Prepare a review copy

```powershell
.\.venv\Scripts\python.exe scripts\prepare_github.py
.\.venv\Scripts\python.exe scripts\prepare_github.py --export
```

The second command creates a timestamped review copy under `reports/generated/github-preparation` and a sibling file-hash manifest, preserving earlier copies. It uses temporary Git metadata to apply ignore rules; it does not initialize the project repository, stage, commit, push or call GitHub. Re-audit after changing source files.

`scripts/verify.ps1` verifies dependencies, backend tests, both frontend builds, public bundle boundaries and rendered guided routes. CI runs these checks on Windows with Python 3.11 and Node 24; optional model tests can skip in base-only environments. CI uses no generation credentials, downloads no model weights and has no deployment step. Remote success is pending an approved push and an actual Actions run.

## Publication authorization — 2026-10-27

- The owner supplied `https://github.com/elkasabyomar27` and explicitly instructed “commit and push” after preparation. Target: public `elkasabyomar27/alethia`, branch `main`.
- An original-code reuse license has not been selected; the existing notice in `LICENSING.md` is retained rather than assigning one without approval. Third-party attribution remains recorded.
- This approval covers the initial source publication. Subsequent commits and pushes require approval.

The current Vercel release remains independently deployed. Creating a GitHub repository does not connect it to Vercel or enable automatic production releases.

## Verification — 2026-10-27

- The clean public copy, with no private dataset or local configuration, passed **222 backend tests**, with one model-artifact-dependent test skipped and one existing upstream deprecation warning. Dependencies came from the existing verified project environment; a new dependency installation was not performed for this preparation.
- Targeted local benchmark/privacy checks passed **12 tests**, including the complete local 150-question pack and rejection of a non-test question in the optional private file.
- Python dependency consistency, local and guided TypeScript/Vite builds, public-bundle audit and all five rendered guided-route/state contracts passed.
- Publication candidate scan passed; file paths, sizes and SHA-256 hashes accompany each clean review copy under ignored `reports/generated/github-preparation/`.
- Remote GitHub Actions has not run. No model generation, paid service, Vercel redeployment, repository creation, Git initialization in the project, commit or push was performed.
