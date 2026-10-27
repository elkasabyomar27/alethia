# Phase 3b — Saved conversations and Gemini generation

## Scope and user-directed change

The user requested Gemini generation instead of a local LLM because of RAM pressure, superseding the earlier all-local generation requirement. Retrieval, uploads, SQLite, and embeddings remain local. Gemini is now the explicit default; Ollama remains an opt-in mode with no automatic fallback. The user chose to configure a replacement key later. The supplied chat credential was not used, copied into files, or used in tests.

This milestone also implements the already-authorized saved-history/context work interrupted by that change. No new packages, model downloads, commits, or pushes were needed.

## Provider contract

Default model: `gemini-3.1-flash-lite`, listed in the [official model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite). The client uses the documented [Generate Content structured-output API](https://ai.google.dev/gemini-api/docs/generate-content/structured-output), with the same Pydantic claim/evidence schema used by backend validation.

The backend reads only whitelisted generation settings from the ignored root `.env` (16 KiB maximum) or environment variables. Environment variables take precedence. There is no frontend key field, `VITE_` credential, query-string credential, cloud credential in reports, or raw provider-error forwarding. The key is sent only in the `x-goog-api-key` header to fixed HTTPS host `generativelanguage.googleapis.com`. The adapter uses a 60-second socket timeout, 16 KiB request / 64 KiB response limits, and 1,024 output tokens. Redirects, tools, automatic retries, and automatic model/provider fallback are absent. Rate-limit/quota errors return 429; authentication, safety/truncation, and transport failures withhold the answer.

Google lists a [free tier and its data-use conditions](https://ai.google.dev/gemini-api/docs/pricing). The application cannot inspect project billing or guarantee zero charges on a billed project. Use an unbilled/free-tier project and fictional demo documents. This change requires internet and sends questions/selected passages to Google; it does not upload full documents, indexes, or earlier turns.

`configured` means only that a key is present. Readiness does not perform a remote call or claim the key works. Live connectivity, quota, schema compatibility, and output quality remain unverified until replacement-key setup. Hosted weights have no local digest: responses store `provider`, requested model, and returned `modelVersion` when available. Historical Ollama answers keep their original digests.

Gemini bypasses local LLM GPU checks, model-load reservations, and unload operations. Dense retrieval still uses its existing memory admission/cap. The previously running idle Ollama server was stopped; local model files were preserved. No unrelated application was closed.

## Durable local conversations

`alethia-conversations.sqlite3` sits beside the document database, with its own schema version 1. The primary document database remains schema 3 and the encoder snapshot is reused. Conversation writes use `BEGIN IMMEDIATE`; generation itself holds no conversation write transaction.

- Up to 100 conversations, 30 turns each, 32 KiB serialized response per turn.
- New conversations are created only when a response is successfully appended; provider errors do not leave empty conversations.
- Existing conversations require `expected_revision`. Compare-and-swap is checked before generation and again before saving, preventing concurrent-tab lost updates.
- Deletion cascades to turns. A late answer cannot recreate a deleted conversation.
- Browser bookmarks carry `#oracle?conversation=<id>` and restore saved turns after reload/restart.
- UI deletion requires confirmation. New conversation does not delete old history.

Saved source snapshots retain document/source/chunk IDs, document revision, exact offsets, supplied text, claims/quotes, model/prompt provenance, and generation diagnostics. On load, citations are checked against current document revision, parent ownership/bounds, and exact normalized text. Changed/deleted sources are labelled and links disabled; no automatic replacement with a different passage occurs.

Deleting a Library document does not remove saved historical quotes. Delete the conversation to remove its logical snapshots. SQLite deletion is not secure erasure. There is no multi-user access control; this remains a single-user local application with cloud generation.

## Context and conservative checks

`sentence-windows-v1` splits source passages at sentence/paragraph boundaries while retaining exact codepoint offsets. Seeds prefer lexical overlap with the question within already-ranked hybrid candidates, including evidence near passage ends. Overlapping windows from one parent are deduplicated. Useful seeds are offered space before contiguous neighboring sentences grow in rounds. Oversized sentences are omitted instead of cut mid-word; a smaller unrelated sentence is not substituted for a higher-overlap sentence that cannot fit.

The inherited 3,456-byte serialized-message budget remains deliberately small; for Gemini this is an application byte budget, not its advertised context length or a claim about its tokenizer. At most three supplied sources are selected. The output schema and question follow the existing explicit instruction/data boundaries.

Recognizable English/Arabic role/instruction patterns can exclude a source or reject a request before generation. Obvious anaphoric questions such as “What about it?” / “طب وده؟” return `needs_clarification` rather than infer a product from older model claims. Prior turns remain display/history only and are not sent to the model.

A narrow numeric-coverage check withholds answers to recognized how-many/how-much questions if the claim text contains no recognized numeric expression. This catches the earlier unrelated opened-product answer to a days question. It does not check the number is correct, all requested facets are covered, product scope is correct, or evidence entails a claim. Recognizers can miss attacks/ambiguity and can falsely abstain on legitimate material. Tests explicitly include an obfuscated attack that passes the filter and a wrong numeric answer that passes coverage. These are not comprehensive security or correctness controls.

## Tests and live observations

184 backend tests and `pip check` pass, with one existing upstream deprecation warning. The production frontend build passes (36 modules; JS about 267.26 kB / 83.31 kB gzip). Tests cover conversation restarts, ordered snapshots, conflicts, rollback, capacity, deletion races/cascade, changed/deleted sources, Unicode offsets, complete boundaries, numeric withholding, recognized attacks, and heuristic limitations. Gemini tests use dummy keys and mocked HTTPS only: headers, schema, response limits, error sanitization, quota behavior, no redirects/retries, missing-key gating, and no local LLM GPU/reservation operations.

Before the Gemini change, two live local v4 diagnostics ran against the existing 29-chunk corpus. The English window question returned the quoted 14-day rule and saved successfully (~7.00 seconds). Egyptian delayed-order evidence was selected from the passage tail, but the draft wrongly phrased contacting support as an action performed by the assistant; its quote did not establish the whole claim (~9.50 seconds). Sampled free RAM dipped to about 668 MiB during that local run, reinforcing the user's reason for switching. Both old reports are ignored under `reports/generated/phase3b-*.json`. These are development observations, not benchmark scores or proof that Gemini fixes quality.

The running Gemini configuration was checked without an API key: status reports `key_missing`, a factual ask returns 503 before inference, and the two saved development conversations remain unchanged. No live Gemini calls were made, including with the credential supplied in chat. User configuration is pending by explicit preference.

The browser restored a saved answer after reload, and Gemini setup correctly disabled Ask while the replacement key was absent. Mobile 390×844 and desktop 1440×1050 layouts showed no horizontal overflow; the final browser error-log check was empty. The current Library copy directs users to The Oracle rather than claiming generation is absent. Final frontend output is about 267.29 kB JS / 83.33 kB gzip. The original six documents / 28 sources and schema 3 matched the pre-milestone content/identity digest. A setup preview was saved outside the repository.

## Next action

Continue claim relevance/scope and adversarial development checks before calling Phase 3 fully validated. Keep failures, returned model versions, sample sizes, and provider configurations distinct from prior Ollama observations. Real quota failures remain unverified; their contract is covered by mocks. Human tickets remain Phase 4; reviewed evaluation remains Phase 5.

## Gemini activation — 2026-10-26

The user subsequently configured the key privately. The API was restarted and three real Gemini requests were made using fictional policy evidence. No credential value was displayed, copied into a report, or passed on a command line.

| Functional sample | Observed result | Server time | Provider request time |
| --- | --- | --- | --- |
| English return-window question | 14 calendar days, with the matching quote | 4.96 s | 2.52 s |
| Arabic opened Aster lamp / change-of-mind question | Said it cannot be returned for that reason, citing the named-product restriction | 3.69 s | 1.38 s |
| Live stock count | `needs_human` / `insufficient_evidence`; no invented count | 3.88 s | 1.68 s |

All three returned hosted model version `gemini-3.1-flash-lite` and saved successfully. Their claims, persisted model version, normalized document slices, matching quotes, and current citation labels were checked through local API reads. Reports remain ignored under `reports/generated/phase3b-gemini-{english,arabic,unsupported}.json`. The sampler recorded minimum available RAM of approximately 994, 1050, and 900 MiB; local embedding admission still applies, and no local LLM was used. These three inspected development outputs are not human-reviewed benchmark items, correctness/faithfulness scores, a latency distribution, or proof of comprehensive abstention.

The browser restored the Arabic Gemini answer, its citation highlighted the matching quote in the Library, and answer provenance displayed the hosted model version. The final browser error-log check was empty; a live-answer preview was saved outside the repository. Original six documents and 28 sources retained their identity/content digest, with no index rebuild. No code changes, commits, or pushes were required for activation.
