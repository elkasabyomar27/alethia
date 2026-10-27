# Phase 2a · Athena’s Library

## Scope and acceptance criteria

- Upload a bounded UTF-8 TXT/Markdown file from the UI; reject empty, binary, invalid UTF-8, unsupported, and over-limit input without storing a partial record.
- Persist extracted text, content identity, metadata, and inspectable source segments in SQLite between API restarts.
- Recognize Markdown ATX headings outside fenced code; preserve section hierarchy, source lines, and offsets in the normalized text. TXT uses a document-level section.
- Detect duplicate normalized content, including changed filenames, UTF-8 BOM, Unicode composition, and line-ending differences.
- Replace a document atomically, preserving the document ID and creation time while increasing its revision and regenerating source segments. Conflicts with another document leave both unchanged.
- Delete document and segments in one transaction, with confirmation in the interface. No vector index exists yet.
- Load six fictional bilingual e-commerce documents through the same ingestion path, atomically and repeatably.
- Verify API edge cases and the actual browser upload/inspect/replace/delete flow; keep the existing React and FastAPI stack.

## Storage and source semantics

`data/local/alethia.sqlite3` is the only persistent application data file in this milestone and is excluded from Git. The path is resolved from the project sources, not the launch directory. SQLite foreign keys are enabled on every connection. Writes are serialized with `BEGIN IMMEDIATE`; the document and source segments commit or roll back together. Connections are explicitly closed after each operation. There is no model or ML dependency loaded by document ingestion.

Normalized text uses strict UTF-8 decoding (optional BOM), NFC Unicode composition, and LF line endings. Arabic content, diacritics, and wording are preserved; this is not an Arabic retrieval normalization step. NUL and other binary/control characters are rejected except newline/tab. The original binary file is not retained. Source offsets and line numbers refer to **normalized extracted text**, not bytes in the uploaded file. SHA-256 identifies normalized content independently of filename and file extension. A duplicate keeps the first record’s filename, format, metadata, and parsing behavior; uploading an identical `.md` as `.txt` does not change it.

Document IDs are stable random IDs. Segment IDs depend on the document ID, normalized content hash, processor version, and ordinal; they persist across restarts and change for changed content. A replacement that restores identical historical content can restore the same content-derived segment IDs. Re-uploading unchanged content does not increment the revision or rename the document.

`text-sections-v1` is deliberately a lightweight inspection processor. It segments within sections at a maximum of 1,200 characters with up to 160 characters of overlap, preferring whitespace boundaries. It recognizes ATX headings, not full CommonMark semantics such as Setext headings. It makes no claim about model token limits. Embedding-aware chunking must be implemented and versioned before dense retrieval; source inspection segments must not silently become model chunks.

Limits: 1 MiB actual request bytes, 200,000 normalized characters, 500 segments per document, 100 documents. Streaming byte counting checks actual data as well as Content-Length. Filename validation rejects paths/reserved characters; filenames are labels and never filesystem paths. Body bytes are not parsed as multipart, avoiding an extra dependency and multipart spooling before upload limits are checked. See the [Starlette request streaming API](https://www.starlette.io/requests/) and [Python SQLite transaction guidance](https://docs.python.org/3.11/library/sqlite3.html).

## API contract

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/api/documents` | List metadata, without full text/segment bodies |
| POST | `/api/documents?filename=policy.md` | Raw file body; 201 new record, 200 duplicate |
| GET | `/api/documents/{id}` | Metadata, normalized text, ordered source segments |
| PUT | `/api/documents/{id}?filename=policy.md` | Raw replacement; 200 updated or unchanged duplicate |
| DELETE | `/api/documents/{id}` | 204 removed; cascade to segments |
| POST | `/api/demo/import` | Atomic import of the six explicitly named bundled demo documents |

Errors use `detail`: 413 limits, 415 unsupported format, 422 invalid text/filename/segment count, 404 missing document, 409 content conflict or library capacity. Pydantic also uses 422 for malformed query parameters. Content-Type is not proof of file validity; text decoding and validation determine acceptance. No arbitrary local path import endpoint is exposed.

## Honest product state

`/api/health` reports version 0.2.0 / `text_ingestion`. `/api/capabilities` reports `knowledge_base: text_documents_ready`, while retrieval stays `not_implemented` and generation `not_configured`. UI counts come from stored records. There is no fabricated indexing progress, quality score, or generated answer.

Markdown is displayed as escaped plain text, including embedded HTML or prompt-like instructions. This prevents rendering uploaded scripts; it does not solve future LLM prompt injection. The local API has no user authentication and must remain on loopback for the single-user development workflow. Multi-user or production exposure needs a separate access-control design.

## Verification record

- 26 targeted backend tests passed against temporary isolated databases: validation/stream limits, English/Arabic text, offsets, Markdown fences, normalization, replacement conflicts, cascade deletion, cross-app persistence, demo idempotency/rollback, concurrency, and forced database-write rollback.
- Strict TypeScript and Vite production build passed. No new application dependencies or ML weights were required; API/test dependencies were installed into a fresh project virtual environment.
- The fresh environment passed all 26 tests and `pip check`; its dependency snapshot is in `backend/requirements-lock.txt`. One upstream Starlette/AnyIO deprecation warning was observed.
- Browser checks passed for import, duplicate upload, new bilingual TXT upload, replacement with revision increment, and deletion confirmation/cancellation. A live DELETE through Vite removed the disposable test document; six demo records remain. See the checklist for layout verification.

## Next step

Phase 2b: bounded PDF/DOCX extraction with page/section references and safe handling of no-text or malformed files. Then implement embedding-token chunking and BM25 before loading the provisional multilingual encoder, adding FAISS persistence, and testing hybrid retrieval. No model-quality conclusion follows from this milestone.
