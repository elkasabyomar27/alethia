# Phase 5b — Benchmark preparation and review workbench

## Delivered and remaining

The candidate pack expanded from 12 to **60** questions: 20 English, 20 Modern Standard Arabic, and 20 Egyptian Arabic across 20 intent groups. Sixteen groups / 48 questions are development candidates; four groups / 12 questions are reserved test candidates. Each group stays within one split. Original IDs and all original 12 examples are unchanged, preserving the existing local draft and historical report snapshots.

The pack includes factual, paraphrase, multi-document, unsupported, and ambiguous requests. New answerable groups include English and Arabic quote candidates. These are agent-authored labels, not reviewed judgments. There are **zero human review attestations**. This milestone does not reach the approximately 150 reviewed-question target or freeze a final benchmark.

The source container remains `data/benchmarks/development.json` for compatibility; it now contains both candidate splits. Dataset ID is `helios-candidates-v2`. Reserved groups were assigned during preparation before running the expanded development diagnostic. They are excluded from the development dataset API, review editor, review packet, preflight details, and retrieval runner. No reserved-test retrieval experiment was run. The source file is readable locally: withholding in this application is a workflow boundary, not encryption or access control.

Do not move a tuned development case into the final test set. Reserve additional new intent groups while expanding, arrange separate test-label review, and record a versioned final freeze only after review. The current reserved labels have not been human-reviewed, and this UI intentionally cannot approve or edit them. A separate test-review/final-test execution workflow remains unfinished.

## Review workflow

Themis provides language, review-status, and question/ID/intent search filters, with matching counts. The default backlog includes unreviewed, draft, and stale cases. **Select next unreviewed candidate** advances within that filtered backlog and does not approve or save anything. Filters preserve the current editor; selecting another candidate discards unsaved edits, as the interface states.

Inspect supporting quotes in Athena’s Library, check the reference answer and answerability, and find all relevant evidence, including equivalent English/Arabic passages. Exact quote matches only establish source locations; they do not establish a correct reference or complete relevance labels. Existing candidate labels can still be incomplete. Correct them before recording your own attestation. A name and the personal-review checkbox are required for approval; saving without it remains a draft. No human attestation was made by the agent.

**Export development review packet** downloads a JSON snapshot of the 48 development references, labels, revisions, review states, and corpus/development fingerprints. It excludes reserved question contents. It does not approve labels or automatically import offline edits; record changes through the revision-checked UI. Exports retain potentially private content, so keep them private when using private documents.

## Evidence preflight and split safeguards

**Check development evidence** checks unique document/quote resolution and source containment. With a current encoder snapshot, it verifies artifact integrity and complete quote containment in encoder chunks. It reads the prepared index without starting an embedding or generation worker. If no current encoder is available, it clearly reports source-only checking. Results show per-candidate issues and development language/category/review distributions. Unsupported cases show no positive labels; this does not validate their answerability judgment.

Preflight rejects a corpus change or encoder rebuild during checking. Its result is a timestamped snapshot; rerun after changes. It does not score retrieval or certify correctness. Failed mappings are visible for repair; they are not silently treated as negative labels.

Dataset loading rejects duplicate normalized question text, intent groups crossing splits, and identical/contained labelled quotes crossing splits in the same document. Question normalization uses Unicode NFKC, case folding, and collapsed whitespace. Review saves apply the same checks to current development overlays and reserved seeds within the review write transaction, preventing an edited question/label from bypassing the seed checks. Rejections give a generic conflict message without exposing reserved contents.

These checks cannot detect all semantic leakage, paraphrases under mistaken groups, or indirect evidence overlap. Human review of grouping and label completeness is still required. Sharing the same retrieval corpus across splits is intentional; split isolation concerns questions and judgments, not withholding business documents from retrieval.

## Actual validation — 2026-10-26

- **216 backend tests** pass, with the existing upstream Starlette/AnyIO deprecation warning. After adding bilingual evidence candidates, the eight preparation tests were rerun and passed. `pip check` passes.
- Strict frontend production build passes: 38 modules, JS 294.46 kB / 89.92 kB gzip.
- A temporary demo database verified every candidate quote against source text. Live preflight verified all 48 development cases against the current document/chunk corpus: zero invalid mappings, 16 candidates per language. This is structural validation, not human review.
- Tests prove reserved contents stay out of packets, preflight and diagnostic traces; normalized duplicates, contained cross-split labels, and conflicting review edits are rejected. Temporary synthetic fixtures also verify preflight makes no retrieval calls and aborts on a corpus change.
- One live UI-triggered BM25 diagnostic, `5efcaff5100e46fb893d438ef10ce628`, completed all 48 development queries on the existing 29-chunk corpus. Scored count is **zero**, with all quality metrics null. No reserved question was retrieved. Observed single-pass median was **9.37 ms**, p95 **11.92 ms**; these are diagnostic timings, not a performance improvement claim or quality benchmark.
- Historical reports retain their own dataset/configuration snapshots. The report notice now names its dataset version so an older 12-question report is distinguishable from the current pack. Earlier reports and the original draft remain preserved.
- Browser checks covered Egyptian Arabic/question/status filtering, empty reviewed backlog with disabled next navigation, preserved draft selection, and a new Arabic quote opening at the exact highlighted Library span. No candidate was approved or changed through these checks.

The original six documents / 28 sources were verified unchanged. No generation request, new project dependency, model download, commit, or push was made for this milestone. Mobile/desktop checks and preview are recorded in the project checklist.

## Next work

Expand toward approximately 150 questions without filling the pack with trivial near-duplicates. Personally review reference completeness, unsupported labels, and cross-language relevance. Preserve reserved groups from tuning and arrange their separate review. Then freeze a reproducible benchmark version, compare BM25/dense/hybrid on reviewed development cases, and add uncertainty and representative failure analysis. Optional reranking and all generation/citation/abstention/handoff quality evaluation remain open.
