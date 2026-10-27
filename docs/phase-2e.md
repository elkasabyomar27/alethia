# Phase 2e — RRF hybrid retrieval

## Outcome and acceptance

The Library combines BM25 and E5 / FAISS rankings on the existing encoder corpus. It exposes exact source links, each retriever’s rank/raw score/contribution, candidate counts, configuration version, and corpus identity. Original-source BM25 remains the default; individual encoder BM25 and dense modes remain available.

Acceptance checks:

- Rank-only fusion agrees with an independent rational-number reference.
- Missing candidates contribute zero; raw BM25/cosine magnitudes do not affect fusion.
- Exact ties use chunk ID, and separate chunks of one parent remain separate results.
- Candidate depth is fixed independently of the displayed result count.
- Both components use one immutable generation; changed/deleted sources cannot escape validation.
- Resource limits and component failures produce explicit errors without a partial hybrid response.
- English, Modern Standard Arabic, and Egyptian Arabic execute locally with exact source slices.
- Backend regression checks and strict frontend compilation pass; browser explanations/source links work on desktop/mobile.

## Fusion contract

The implementation follows the rank-based formula in [Cormack, Clarke, and Büttcher, SIGIR 2009](https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf):

```text
score(chunk) = sum(1 / (60 + rank)) for each candidate list containing chunk
```

Ranks are one-based, with equal unit weights. Each component supplies up to 20 candidates. These are provisional, versioned defaults, not settings tuned against ALETHIA benchmark questions. Missing candidates contribute zero; they do not indicate that a document lacks relevant evidence. An empty successful BM25 candidate list is valid. A failed retriever is an error, not an empty list.

Raw BM25 and cosine scores are retained only for inspection. They are neither normalized together nor added. Candidates deduplicate by encoder chunk ID. Duplicate IDs within a retriever or conflicting source metadata fail closed. Exact fused-score ties sort by chunk ID. `top_k` truncates only after fusion: changing 3/5/10 displayed results does not change the candidate pool or the ranking prefix.

Configuration version: `equal-rrf-60-depth20-v1`. The depth limits the union to at most 40 candidates. The FAISS exact search already scores the whole bounded corpus before selecting candidates; this milestone does not add another model or perform multiple query embeddings.

## Architecture and API

`app/rag/fusion.py` contains the small dependency-free rank function. `DenseIndex.search` acquires the same embedding admission guard and generation lock as dense search, runs one query embedding/FAISS retrieval, obtains BM25 candidates from that generation’s chunk database, fuses, then revalidates the primary source revision/fingerprint while resolving exact passages. An upload during either component rejects the response with 409. No encoder rebuild, schema migration, package installation, or model download is required for this milestone.

API request:

```json
{"query":"What is the return policy?","method":"hybrid","top_k":5}
```

Hybrid defaults to `corpus: "encoder"`; an explicit `source` corpus is rejected (422). The existing BM25 default/API behavior remains intact. The response includes:

- `index.method: "hybrid"`, `match_mode: "rank_fusion"`, and the shared `corpus_hash`.
- `index.fusion`: rank constant, candidate depth, weights, actual candidate counts.
- Per-hit `retrievers.bm25` / `retrievers.dense`: rank, raw score, contribution, or null when absent from that candidate list.
- Fused `score`, exact source/offset provenance, and measured server search latency.
- `worker_diagnostics`: embedding-worker duration/memory only; overall server latency includes both components, fusion, integrity checks, and source resolution.

Health version is now `0.2.4`, phase `hybrid_retrieval`. Capabilities report hybrid snapshot/runtime availability separately. Readiness does not reserve RAM or guarantee the next operation can run.

## UI and resource behavior

Choose **Hybrid · BM25 + semantic (RRF)** in Athena’s Library. **Why this passage ranked here** explains each candidate contribution, with raw scores clearly labeled. **Search configuration** records the actual candidate counts and fusion parameters. Scores are explicitly not confidence or answerability estimates. The search button waits for the current index status after a mode change.

Existing CPU safeguards remain: one embedding operation per API process, 1 GiB available RAM required at admission, 768 MiB worker allocation cap, two threads, and a 30-second embedding-query timeout. Workers unload after queries. Hybrid errors do not silently switch to a baseline; users can choose another mode explicitly. A missing/low-memory/busy encoder or failing BM25 component blocks a hybrid response. Reranking is still optional and deferred; no additional model is loaded on this 8 GiB machine.

## Validation and practical limits

All 121 backend tests pass, with one existing Starlette/AnyIO deprecation warning. `pip check` passes. The frontend passes strict TypeScript and production compilation. New checks include independent fraction-based RRF scores, missing candidates, score-scale invariance, duplicate/conflicting identities, exact ties, candidate pool depth larger than requested results, rank-prefix consistency, source offsets, restarts through a new index manager, no fallback on either component failure, admission-guard release, and changes between components. Synthetic vectors in lifecycle tests exercise mechanics only.

The real pinned encoder snapshot was reused without rebuilding: six documents, 28 parent sources, 29 encoder chunks. Live API checks covered one English, one MSA, and one Egyptian Arabic question, independently verified fused arithmetic, exact source text slices, and top-3/top-10 prefix consistency. The first files were returns, returns, and shipping respectively. Actual candidate counts were 20/20, 4/20, and 2/20 (BM25/dense). Observed server times were about 2.30–2.33 seconds for these three requests. These are single-run functional observations, not a latency distribution or retrieval-quality benchmark. Full local responses are ignored under `reports/generated/phase2e-live-checks.json`.

Browser checks verified the Egyptian Arabic hybrid results, both component ranks and contributions, actual candidate counts, exact source highlighting, and source bookmark reload. Desktop 1440×1050 and mobile 390×844 layouts showed no horizontal page overflow, including expanded explanation/configuration content. The final browser error-log check was empty. A preview was saved outside the repository. No primary document/source edits, new dependencies, model downloads, commits, or pushes were made during this milestone.

No quality improvement is claimed. Rank fusion can promote irrelevant passages, corpus vocabulary affects BM25, dense scores do not establish answerability, and chunk overlap can repeat evidence from one parent. A near-duplicate diversity strategy and reranking should be evaluated later rather than assumed beneficial. The 150-question human-reviewed dev/test benchmark is still required in Phase 5. No generated answers, citations in generated prose, or handoff decisions exist yet.

## Next milestone

Phase 3a — The Oracle: inspect local Ollama availability and hardware capacity, select and measure a feasible quantized instruct model, then connect bounded grounded generation with traceable citations and conservative uncertainty handling. Keep encoder/LLM memory lifecycles explicit. Do not claim end-to-end generation quality until it has been evaluated.
