# Phase 2c · BM25 and source-linked search

## Acceptance criteria

- Search stored source passages using an explicit BM25 lexical baseline, with English/Arabic query normalization.
- Persist the lexical index and update it atomically with ingestion, replacement, and deletion.
- Keep retrieval separate from generation; return no fabricated answer, answerability decision, or confidence percentage.
- Return exact source IDs, text offsets, PDF pages, Word structural references, document revisions, and extraction notes.
- Provide inspectable ranking scores, query terms, configuration, and measured server search time.
- Support source permalinks, reload, and stale-source detection, including inspection of already-open cached sources.
- Validate the scoring mathematics and index consistency; do not present smoke examples as retrieval benchmarks.

## Retrieval architecture

The installed Python runtime provides SQLite 3.38.4 with FTS5. The baseline uses native FTS5 BM25, requiring no new Python packages or model downloads. Retrieval code lives in `backend/app/rag`; the route is separate from any future generation adapter.

Schema 3 adds `lexical_segments`, an external-content FTS5 table (`segment_search`), analyzer/build metadata (`lexical_config`), and synchronization triggers. Lexical rows have an `INTEGER PRIMARY KEY` and reference immutable source IDs. This keeps the mapping stable across SQLite VACUUM operations rather than depending on ordinary source-table rowids.

Source insertion populates normalized lexical text through a registered deterministic SQLite function. Foreign-key cascades and triggers remove deleted passages. Index and document changes commit or roll back together, including replacements and failed ingestion. Migration explicitly backfills existing sources; creating triggers alone would not index old rows. The schema-2 local database was backed up first, and original source identities were verified unchanged after migration.

An analyzer version change rebuilds only the derived index in the startup transaction. The persistent index revision advances on committed lexical changes; it is an index mutation counter, not a document count. `built_at` records a full build/rebuild, not the time of the latest upload. Use the application API/store for writes: the normalizer and foreign-key enforcement are registered on every store connection.

Search counts, corpus statistics, hits, and source metadata are read within one SQLite snapshot. A writer’s uncommitted replacement is invisible to search. There is no in-memory copy of the whole corpus and no model initialization at API startup.

## Frozen baseline configuration

| Setting | Value |
| --- | --- |
| Retriever version | `sqlite-fts5-bm25-v1` |
| Analyzer | `en-ar-lexical-v1` |
| FTS tokenizer | `unicode61 remove_diacritics 0` over pre-analyzed words |
| BM25 constants | k1 = 1.2, b = 0.75 |
| Indexed unit | One stored source segment |
| Indexed fields | Segment text only; no filename/section metadata boosts |
| Query matching | OR across distinct analyzed terms; no query-frequency boost |
| Tie-breaking | Score, document content hash, segment ordinal, source ID |
| Segmentation | Existing character-based segments, with each source’s processor version returned |

The API negates SQLite’s negative BM25 result so higher displayed scores rank first. SQLite floors nonpositive inverse-document-frequency values to `1e-6`. The independent test calculation includes this variant; future comparisons must record the exact variant and chunking configuration. See the [official FTS5 documentation](https://www.sqlite.org/fts5.html) for native ranking and external-content index behavior.

The displayed score is not normalized across queries/corpora and is not evidence of factual correctness. Server search time uses a monotonic clock around normalization, snapshot retrieval, and hit construction. It excludes HTTP transport, response serialization, and browser rendering. Individual query timings are not p50/p95 benchmark measurements.

## Query/source normalization

Normalization runs identically on indexed passages and queries while preserving source text:

1. Unicode NFKC and case folding.
2. Arabic alef variants (`أ إ آ ٱ`) map to `ا`; `ى` maps to `ي`; tatweel is removed.
3. Arabic combining vocalization/annotation marks are removed.
4. Unicode decimal digits, including Arabic-Indic and Eastern Arabic-Indic forms, map to ASCII digits.
5. Unicode letters/digits form words; punctuation separates them.

No stemming, clitic stripping, stopword removal, translation, or synonym expansion is applied. `ة`/`ه` and hamza carriers remain distinct. Original English/Arabic text, diacritics, and citation offsets remain in the document store. This is a lexical baseline, not a claim of cross-language or dialect semantic understanding. Python 3.11 and the runtime SQLite version must accompany future reproducibility reports.

## API

| Method | Path | Contract |
| --- | --- | --- |
| GET | `/api/retrieval/status` | Actual index/source counts, state, revision, analyzer, SQLite version, and parameters |
| POST | `/api/retrieval/search` | JSON `{ "query": "return policy", "top_k": 5 }` |

Queries accept 1–500 characters after validation and at most 64 distinct analyzed words; `top_k` is an integer from 1–10, default 5. Whitespace/punctuation-only queries and unknown request fields are rejected with 422. User-supplied MATCH operators never become executable query syntax: analyzed words are individually quoted and SQL values are bound.

Responses include the query, normalized terms, index snapshot, measured `latency_ms`, and ordered hits. Each hit contains rank, positive score, matched normalized terms, document/source IDs, filename, revision/content hash, processor version, full segment text, offsets/lines, page or paragraph/table locator, and extraction notes. No-match results contain an empty hit list and make no unsupported-question abstention claim. Empty libraries and sources with no searchable words are explicit.

Capabilities now report `retrieval: bm25_ready`, version `0.2.2` / phase `lexical_retrieval`. Dense retrieval, hybrid fusion, generation, evaluation, and tickets remain pending.

## Source inspection workflow

Results link to `#library?document=<document-id>&source=<segment-id>`. The Library selects the correct document, switches to segmented view, highlights the exact source, and moves focus to it. Links survive reload. Inspection fetches the current document even for a repeated click on the same already-open source URL. Deleted documents and replaced passages show explicit errors rather than silently selecting another source. Normal navigation clears the stale selection.

Search results are snapshots and show document revision numbers. Library mutations/refresh invalidate displayed results; external changes are revalidated when a source is opened. The query text is kept in browser state only; no new conversation history or question logs are persisted.

## Verification and known limitations

- 83 backend tests pass in the isolated environment, including 25 retrieval cases. The existing upstream Starlette/AnyIO deprecation warning remains.
- An independent formula checks native BM25 scores on a controlled corpus, including common-term IDF flooring and duplicate query-term handling.
- Tests cover Arabic normalization without source mutation, empty/no-match queries, literal operator handling, deterministic ties across import order, bounds, PDF/Word provenance, duplicate uploads, replacement/deletion, forced rollback, restart/VACUUM persistence, snapshot isolation, old-schema backfill, analyzer-version rebuild, and native FTS integrity checks.
- The frontend passes strict TypeScript/Vite build; dependency compatibility passes. No dependency or model weight was added.
- A real API restart preserved the full index build metadata, source IDs, ranking, and scores. Desktop 1440×1050 and mobile 390×844 layout checks found no horizontal overflow.
- Browser checks cover English and Egyptian Arabic searches, exact source focus/highlighting, reloadable permalinks, no-match messaging, replaced/deleted source links, and inspection after an external replacement while the old source remains cached. Disposable test data is removed; the six original demo documents and 28 original source segments remain unchanged.

A representative smoke-test failure: `لو الأوردر اتأخر أعمل إيه؟` retrieves the intended shipping passage but also an unrelated payment FAQ sharing `إيه`. This is recorded as a lexical limitation, not silently optimized away or reported as an aggregate quality score. English word forms, Arabic clitics, and synonyms can also miss relevant passages. Reviewed references and a frozen development/test split are still required before quality benchmarking.

The source segments remain character-based. Before comparing BM25 with dense/hybrid retrieval, freeze one shared encoder-aware chunk corpus and rerun all methods against it; do not compare scores from different segmentation regimes as if they were equivalent. There is no Recall@5, MRR, generation quality, or language-wide accuracy claim from this milestone.

## Next milestone

Phase 2d: recheck available memory, introduce encoder-token-aware chunks with source mapping, trial the provisional multilingual embedding model on CPU, and add persisted FAISS dense retrieval. Measure actual resource use before loading larger models; keep the current BM25 baseline reproducible when its chunk corpus changes. Hybrid RRF follows once both retrievers are verified.
