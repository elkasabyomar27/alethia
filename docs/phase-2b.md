# Phase 2b · PDF and DOCX ingestion

## Acceptance criteria

- Accept bounded text-based PDF/DOCX files through the existing upload and replacement API/UI.
- Preserve physical PDF page numbers, including gaps caused by pages with no extractable text.
- Preserve Word heading hierarchy, body paragraph ordinals, and table/row references without inventing page numbers.
- Reject malformed, encrypted, image-only, over-limit, and unsupported documents without partial database writes.
- Bound parser time, memory, decompression, document complexity, and concurrency on the target Windows machine.
- Migrate existing data without changing old documents, revisions, text, or source IDs.
- Show extraction limitations and skipped pages explicitly in Athena’s Library. Continue to report retrieval as unimplemented.

## Implementation and dependencies

`pypdf==6.21.2` extracts PDF text in a worker. DOCX uses `zipfile` and `defusedxml==0.7.1` for a bounded Office Open XML subset. This avoids an office renderer or a large dependency stack in the running application. Both new wheels total under 0.5 MB and require no ML models, paid services, or external requests. The runtime dependency lock was updated. Package metadata declares pypdf under BSD-3-Clause and defusedxml under the PSF license.

Every binary upload starts a short-lived child process using the current Python interpreter and the fixed `app.parsers.worker` module. Payloads pass through stdin; structured JSON returns through stdout. Filenames never become commands or extraction paths. The worker does not render documents, execute macros/scripts, open hyperlinks, extract ZIP entries onto disk, or perform OCR. This is a resource-limited parser process, not a claim of a complete operating-system security sandbox.

## Resource budgets

| Resource | Limit |
| --- | --- |
| Raw upload | 1 MiB, counted while streaming |
| Normalized extracted text | 200,000 characters |
| Source segments | 500 per document |
| Library capacity | 100 documents |
| Concurrent binary workers | 1 per API process; additional requests receive 503 for retry |
| Worker timeout | 10 seconds; timed-out child is killed and reaped |
| Worker committed memory, Windows | 256 MiB via a Job Object; child-process count limited to 1 |
| PDF physical pages | 50 |
| Decoded PDF page content | 1 MiB per page / 4 MiB cumulative |
| PDF decoded stream | 2 MiB, with additional parser structural/work budgets |
| DOCX ZIP entries / expanded bytes | 256 entries / 8 MiB declared expanded total |
| DOCX XML entry | 2 MiB |
| Parsed DOCX XML | 30,000 nodes / depth 64 per parsed XML part |
| DOCX nonempty paragraph/table-row blocks | 500 |

ZIP expanded sizes and entry count are checked before decompression; read XML parts undergo CRC checks and entity/DTD rejection. The worker cap and timeout remain the final guards against parser behavior outside those checks. Memory protection fails closed (503) if it cannot initialize. Non-Windows systems use a 256 MiB address-space limit, but that path has not been exercised on this machine. Run a single backend process with the documented command; multiple API processes would each have their own worker slot.

The pinned pypdf public configuration API bounds decompression, array/dictionary sizes, page-tree complexity, form invocation counts, and decoding/parsing work. External JBIG2 decoding is disabled. See the [upstream PDF extraction guidance](https://github.com/py-pdf/pypdf/blob/main/docs/user/extract-text.md) for why raw file size is insufficient to bound extraction memory.

## Extraction semantics

PDF extraction runs in strict mode. Non-PDF signatures, malformed structures, encrypted files, and excessive complexity are rejected with actionable messages. Each nonempty page becomes a source range; a long page can generate multiple inspection segments, all retaining its page number. Empty/image-only pages are skipped and listed in persistent extraction notes; if all pages lack text, the whole document is rejected. The application does not claim to distinguish blank pages from scans or recognize partially scanned regions on a page that also contains text. Page labels are physical 1-based PDF positions, not printed page labels.

DOCX extracts visible text tokens from ordinary body paragraphs, displayed hyperlink text, tabs/line breaks, and top-level table rows in document order. Standard heading styles, inherited custom styles, and explicit outline levels establish section hierarchy. Paragraph ordinals count top-level body paragraphs, including empty paragraphs; table row numbers count rows within each top-level table. Those are structural references, not Word layout pages. Basic cells are joined with tabs and cell paragraphs with newlines; merged-table structure and visual column geometry are not reconstructed.

Legacy DOC, macro-enabled main document types, unsafe ZIP names, duplicate ZIP entries, unsupported compression/encryption, nested tables, body content controls/other unsupported blocks, tracked insertions/deletions/moves, and imported alternate content are rejected. Images, drawings, text boxes, headers, footers, comments, and footnotes are not extracted; the UI states this limitation. Field values are cached text only; nothing is refreshed or executed.

All accepted text is normalized to NFC and LF line endings, checked for invalid control characters, and displayed as escaped plain text. Source offsets/line numbers refer to the assembled normalized extracted text. Segments remain character-based inspection segments; embedding-aware chunking is a later milestone.

## Provenance, deduplication, and schema migration

Binary files use SHA-256 of the original bytes for `content_hash`, with `hash_basis: original_file_bytes`. TXT/Markdown continue to hash normalized text (`hash_basis: normalized_text`). This deliberately preserves independent PDF/DOCX provenance when their extracted text matches a TXT upload. Identical renamed binary files reuse the first record; re-exported files with changed bytes can be separate documents. Use replacement to keep one logical record across edits. Raw binary bytes are not stored after extraction.

New processor versions are `pdf-sources-v1` and `docx-sources-v1`; existing text documents retain `text-sections-v1`. Segment IDs incorporate the document’s own processor version and content identity, avoiding accidental invalidation of old sources.

Schema version 2 adds nullable page/source-label fields to segments and hash-basis, page-count, and extraction-notes fields to documents. Migration uses one SQLite transaction and only additive columns. Existing content, document/source IDs, timestamps, and revisions remain unchanged. A database with a future version is refused rather than downgraded. Before upgrading the local demo database, a SQLite backup was saved under the ignored `data/local/backups/` directory.

The API now reports version `0.2.1`, phase `document_ingestion`, and capability `document_ingestion_ready`. Retrieval remains `not_implemented`; generation remains `not_configured`.

## Verification

- 58 backend tests pass in the isolated Python environment. Existing ingestion tests remain included; final checks also exercise the PDF decoder cap and cumulative page-stream limit.
- Generated minimal PDF fixtures cover valid pages, skipped blank pages, image-only pages, malformed files, passwords, page count, and compressed expansion. DOCX fixtures cover Arabic, headings, table order, custom styles, invalid archives/XML/entities, unsupported blocks, and input/resource limits.
- Real worker tests verify timeout recovery, the single-worker slot, failure when resource protection cannot initialize, and rejection of a 320 MiB allocation under the actual 256 MiB cap.
- Migration tests preserve version-1 identities and refuse future schema versions. The actual local upgrade preserved all 6 original documents and 28 source segments, verified by comparing original column values and IDs.
- Strict TypeScript/Vite production build and `pip check` pass. The existing upstream Starlette/AnyIO deprecation warning remains; no tests fail.
- Browser checks verified PDF pages 1/3 with a skipped-page-2 note, Arabic DOCX paragraphs/sections, and image-only PDF rejection with no added record. Final layout/cleanup results are recorded in the project checklist.

These are functional and resource-control tests, not a representative document-extraction quality benchmark. Arabic PDF reading order, complex fonts, multi-column layouts, tables, and real-world document variety still need broader validation. No RAG or model-quality scores are implied.

## Next milestone

Phase 2c: add a BM25 retrieval baseline and a source-linked search inspection workflow, preserving document deletion/update consistency. Then introduce encoder-token-aware chunking, measured multilingual dense retrieval, FAISS persistence, and hybrid fusion. Do not download LLM weights or claim retrieval quality before the corresponding tests and experiments.
