# Phase 5c — 150 candidate questions and relevance review

## Outcome

Dataset `helios-candidates-v3` contains **150 agent-authored candidates** in **50 intent groups**, with one English, Modern Standard Arabic, and Egyptian Arabic question per group. Forty groups / 120 questions are development candidates; ten groups / 30 questions are reserved test candidates. Development has 40 examples per language; the reserved split has ten per language.

The previous 60 seed examples were retained and 90 added. New topics cover product specifications, shipping estimates and their starting point, return conditions, damage remedies, warranty boundaries, unsupported individual refunds/repair quotes, cancellation after dispatch, and local support limitations. The pack includes factual, paraphrase, multi-document, unanswerable, and ambiguous cases. All seed evidence grades remain candidate grade 1.

**No human reviews have been recorded.** Reaching 150 candidates does not satisfy the master brief's 150 human-reviewed-question requirement. Structural quote checks are not correctness judgments. Final review, freeze, generation evaluation, reranking, and final test execution remain open. No reserved question was retrieved or sent to a generation model in this milestone.

## Review and provenance changes

Themis shows separate counts for all candidates, development candidates, development review attestations, and reserved candidates. This distinguishes pack size from review progress. Reserved contents remain excluded from the development editor, packet, preflight details, and runner.

Evidence labels can now be assigned grades in the editor: 1 relevant, 2 strongly relevant, 3 essential. Use a consistent interpretation across the dataset: supporting context, direct support for a claim, and decisive evidence needed for the answer, respectively. If reliable distinctions cannot be made, retain binary grade 1 consistently rather than inventing distinctions. A grade change alone does not approve a case. Saving without personal attestation remains a draft, with existing revision and corpus-invalidation safeguards.

Preflight highlights cases whose quotes do not include separate Arabic and non-Arabic candidates. The script-presence heuristic is a prompt to inspect equivalent passages, not language identification, a mandatory bilingual-label rule, a retrieval failure, or a completeness test. Cross-language retrieval can validly use evidence in another language. The reviewer must decide whether additional relevant passages actually exist.

Live development preflight resolved every current label to documents and encoder chunks, with zero invalid mappings. **84 cases** triggered the equivalent-language review prompt. This does not establish 84 actual label errors; nor does the absence of a prompt validate the remaining cases. Incomplete positive labels bias quality metrics, so inspect equivalence before measuring quality.

Dataset responses, review packets, preflight, and new experiment JSON include the complete seed-pack fingerprint, in addition to existing development/review and corpus fingerprints. Reserved contents are represented only through their contribution to this hash and aggregate count in these development outputs. Altering a reserved seed changes the pack hash without exporting its question or reference. Existing reports retain their older snapshots and remain readable.

Pack SHA-256 for this milestone: `0caa4dffb86cbd9ad2d4f88ad6ee37ffd2b62aa0ff22fbdf884a6ea80aeacf2a`. This fingerprint covers serialized example models; the separate dataset ID identifies the pack version. It is a reproducibility identifier, not a signature or access-control mechanism.

## Personal review procedure

1. Filter development candidates by language/status. Read the question and decide whether its intent and answerability are clear. Unsupported labels must be checked against the whole knowledge base, not just a failed search.
2. Inspect the actual document passages. Correct any unsupported or incomplete reference claims, product scope, dates, conditions, and expected handoff/clarification behavior.
3. Add all relevant positive passages, including equivalent English/Arabic passages where present. Use unique exact quotes within source and encoder boundaries. Apply relevance grades consistently.
4. Record your name and personal attestation only after those checks. Saving without the checkbox keeps the case unreviewed. Approval is an attestation, not proof of identity or independent double review.
5. Keep reserved groups out of development tuning. Arrange separate review of reserved labels and establish the final version/freeze before executing a final test. The current development UI intentionally cannot review or run reserved cases; that separate workflow remains unfinished.

These translations/paraphrases are correlated. There are 50 intent groups, not 150 independent customer observations. Future uncertainty estimates should account for grouping; the reserved set has only ten intent groups and cannot support broad generalization. Agent-authored fictional-store examples also do not represent real customer traffic or general Arabic dialect coverage.

## Actual verification — 2026-10-26

All **219 backend tests** and `pip check` pass; the existing upstream Starlette/AnyIO deprecation warning remains. New tests cover cross-language review prompts without approval, reserved-seed fingerprint changes without content exposure, and grade-3 draft persistence without attestation. Existing tests cover pack balance, all source quotes, grouped splits, edited-label leakage checks, metric formulas, and no scoring of unreviewed cases. Synthetic fixtures are not project benchmark results.

Strict frontend build passes: 38 modules; JS 295.54 kB / 90.20 kB gzip. Browser checks confirmed grade editing and reset without saving or checking the personal-attestation box. Mobile and desktop layout checks are recorded in the checklist.

One actual UI-triggered **BM25 development diagnostic** completed 120 queries: `a284183102714eb281129bb81acdee7d`. All 30 reserved candidates were excluded. Every quality metric is null, with scored count zero. Observed single-pass server median was **9.11 ms**, p95 **12.28 ms**. These are diagnostic timings on the existing 29-chunk corpus, not an improvement claim or a controlled performance comparison. JSON/Markdown exports and the report's seed-pack fingerprint were verified. The UI displays four “Awaiting review” quality cells and the correct dataset version.

The original six documents / 28 source segments, prior development records, existing draft, and historical reports remain preserved. No generation API request, model download, project dependency installation, commit, or push was made for this milestone. The next required step is personal reference/evidence review before any defensible quality comparison.
