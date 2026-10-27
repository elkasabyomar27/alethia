# Phase 5a — Themis’ evaluation foundation

## Scope and acceptance

Delivered: portable question/evidence schema, local review workflow, a sequential retrieval runner, transparent metrics, real report UI, and JSON/Markdown exports. This is the foundation of Phase 5, not the completed benchmark.

- Twelve starter development candidates cover English, Modern Standard Arabic, Egyptian Arabic, paraphrases, multiple documents, unsupported and ambiguous questions. They remain agent-authored and unreviewed. No held-out questions are frozen yet.
- Review drafts persist without implicit approval. A personal attestation requires a reviewer name and an explicit checkbox. Every source quote must resolve uniquely. Changing library contents or a seed example invalidates its review. Competing edits return a revision conflict.
- BM25, dense, and hybrid use one encoder chunk corpus. Run reports record the actual dataset/review snapshot, corpus/model hashes, encoder generation, methods, configurations, per-question ranked IDs, exact source offsets, labels, latency, worker diagnostics, and runtime versions.
- Unreviewed and unsupported cases have no retrieval-quality scores. An interrupted or failed experiment has no completed report or partial quality summary. A library change or encoder rebuild aborts publication, including rebuilds with unchanged chunk IDs.
- The dashboard displays only completed reports, with sample counts, language breakdowns, source inspection, measured latency, configuration details, and limitations. Evaluation makes no Gemini, Ollama, judge, or customer-message calls.

## Labels and review

Source candidates live in `data/benchmarks/development.json`. Each example has a stable ID, paraphrase group, split, language/category, question, reference answer or expected behavior, answerability, and filename/quote/grade evidence. The loader rejects duplicate IDs and a group crossing development/test splits. The API exposes only development contents and has no test-run selector. This prevents accidental test execution through these controls; it is not an authorization system or protection against someone reading local files.

Open Themis’ review section, choose a candidate, inspect the quote in Athena’s Library, and check its reference and all relevant evidence. Add/correct labels before recording your own review. The agent did not check the personal-attestation box. One unchanged candidate was saved as a draft to verify the workflow; the remaining eleven are unreviewed. There are zero approved cases.

Evidence quotes must be unique exact slices within a source and fit completely within an encoder chunk. Every chunk containing a labelled quote becomes a positive relevance judgment; overlapping eligible chunks are included. Grades are integers 1–3. Unlabelled chunks count as nonrelevant. Human reviewers must assess label completeness, equivalent passages, and cross-language evidence: merely finding an exact quote does not establish complete relevance judgments or a correct reference answer. Missing positives bias all four metrics.

Unsupported/ambiguous examples retain expected behavior but no positive labels. They are traced and timed; these retrieval runs do not test abstention, generation, or handoff decisions.

## Metric definitions

For a ranked list of unique chunk IDs and positive graded relevance labels:

- Recall@5: positives retrieved in the first five divided by all labelled positives.
- Precision@5: positives retrieved in the first five divided by five, even with fewer than five hits.
- MRR@10: reciprocal rank of the first positive within ten, or zero if absent.
- nDCG@5: DCG divided by ideal DCG, using gain `2^grade - 1` and discount `log2(rank + 1)`. Ideal order sorts all positive grades descending and takes five.

No positive labels means unscored, rather than perfect or zero. Aggregate quality is the macro mean over currently reviewed, answerable cases only. Latency includes all executed queries; median uses the ordinary sample median, and p95 uses nearest rank `ceil(0.95*n)`. A language with no queries has null latency. Timing wraps server retrieval, including integrity checks and embedding-worker startup, excluding HTTP transit and UI rendering. This is not a warm-cache microbenchmark.

Definitions follow standard information-retrieval conventions: Stanford’s [precision/recall discussion](https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-unranked-retrieval-sets-1.html), [ranked retrieval evaluation](https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-ranked-retrieval-results-1.html), and [evaluation lecture covering reciprocal rank](https://cs276.stanford.edu/19handouts/lecture8-evaluation-6per.pdf). Tests use independently calculated examples, cutoffs, short lists, empty labels, graded gains, and macro aggregation.

## Actual diagnostic — 2026-10-26

One live UI-triggered BM25 run completed: `8b33f4fadf564a6391cc134b237e558b`. It executed 12 development queries on the existing 29-chunk encoder corpus: six English, three MSA, and three Egyptian Arabic. All quality metrics are null; scored count is zero. Observed server median was **12.00 ms**, nearest-rank p95 **21.86 ms**. These are single-pass diagnostic timings on this machine, not quality evidence or general performance promises.

Chunk corpus SHA-256: `2cb1edc2e8ad1e3ee4b3c2b84875a794924676d34a5ccea056524b82a17b67b5`.

The JSON contains the complete snapshot and timings. JSON and Markdown attachment exports were checked against it; original Library evidence links resolve to the exact highlighted passage. Dense/hybrid paths were exercised with temporary synthetic encoder fixtures in tests; no real dense/hybrid comparison or reranker experiment was performed in this milestone. No new model download, dependency installation, or generation request was needed.

## Persistence, resource limits, and reproduction

Review overlays and run status use ignored `data/local/alethia-evaluations.sqlite3` (schema 1). Complete JSON reports live under ignored `reports/generated/evaluation/`; publication uses a temporary file and atomic rename. Markdown is generated from the saved JSON. Preserve the JSON and corresponding corpus/model artifacts for reproduction; repeating a run can change timings. Reports are local files, not cryptographically signed or tamper-proof records.

Limits: 250 dataset questions / 1 MiB dataset; eight labels per question; 50 retained runs; 16 MiB per report. Only one evaluation is admitted at once. Use one API process/worker: the startup recovery step marks leftover running jobs interrupted, and multi-process coordination is not implemented. Dense/hybrid use existing sequential worker/RAM safeguards. Concurrent interactive retrieval can affect latency; use an otherwise idle machine for a controlled comparison.

Reports and review overlays retain questions, candidate answers, labels, and retrieved excerpts even if documents are later removed. No retention/deletion UI is included in this foundation. Export/preserve needed reports before intentionally managing local data. Private uploads, databases, generated reports, models, and secrets remain ignored by Git; the public seed pack contains fictional material only.

The UI and `scripts/run_retrieval_evaluation.py` both use the same localhost API. CLI defaults to reviewed-only; `--diagnostic` explicitly includes unreviewed cases. No tuning or final test evaluation is performed automatically.

## Verification and next milestone

All **208 backend tests** pass; `pip check` and the strict frontend production build pass (38 modules, JS 290.69 kB / 88.97 kB gzip). One existing upstream Starlette/AnyIO deprecation warning remains. Tests cover formulas, review revisions/invalidation, split grouping, no implicit approval, interrupted recovery, corpus changes, same-content rebuild rejection, all three retrieval paths, and unavailable report handling. Synthetic unit scores are never displayed as project benchmark results.

The live diagnostic, draft review, exports, source inspection, and API restart persistence were checked. The six original documents / 28 sources remain unchanged. Mobile and desktop layout checks are recorded in the project checklist.

Next: expand and personally review the benchmark, freeze grouped development/test splits, then run controlled BM25/dense/hybrid comparisons with uncertainty and failure analysis. Reranking, generation correctness/faithfulness, citation evaluation, abstention/handoff precision and recall, confidence intervals, and the approximately 150-question reviewed dataset remain unfinished. Do not infer any of these from a successful diagnostic.
