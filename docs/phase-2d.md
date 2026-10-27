# Phase 2d — Local multilingual dense retrieval

## Delivered

Athena’s Library now builds a persisted FAISS index with multilingual E5-small embeddings. Three explicit modes are available: original-source BM25, encoder-chunk BM25, and semantic E5 / FAISS. The latter two use identical chunk IDs and a shared corpus hash. Original BM25 remains the default and works without ML dependencies.

This milestone implements retrieval only. It does not implement hybrid fusion, answer generation, confidence thresholds, abstention, or evaluation quality scores.

## Model and hardware decision

The development machine has 7.82 GiB RAM, an AMD Ryzen 7 7435HS, and an RTX 2050 with 4 GiB VRAM. Available RAM varied substantially during work; a real build attempt was rejected at about 650 MiB free. The 1 GiB admission threshold was retained, and work resumed after memory was freed.

The provisional `intfloat/multilingual-e5-small` choice is retained. To avoid adding a large PyTorch stack on this machine, a small CPU ONNX adapter implements the encoder directly rather than using Sentence Transformers at runtime. This is a deliberate stack adjustment for hardware constraints. No LLM weights or Ollama inference have been added.

- Official model: [multilingual-e5-small, pinned revision](https://huggingface.co/intfloat/multilingual-e5-small/tree/614241f622f53c4eeff9890bdc4f31cfecc418b3). Repository metadata declares MIT licensing.
- Revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`.
- Export: `onnx/model_qint8_avx512_vnni.onnx`; 118,346,824 bytes.
- Model SHA256: `dd476dd0c2514e9b9be83aeb3853fac0763e0bdf4a71645407587d77c48a2d88`.
- Tokenizer SHA256: `0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39`.
- About 130 MiB of downloaded model/tokenizer/config/card files, stored under ignored `models/`.

The official AVX512-VNNI-named export executes through ONNX Runtime’s CPU provider on this AMD machine. Successful inference does not establish numerical equivalence or language quality. [ONNX Runtime’s quantization documentation](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html) describes possible U8S8 saturation on AVX2 hardware. Quantization effects, English/MSA/Egyptian Arabic quality, and this export’s suitability require the reviewed benchmark. Published scores in the downloaded upstream model card are not ALETHIA results.

## Encoder contract and source preservation

The adapter follows the model card’s `query: ` / `passage: ` prefixes, attention-mask mean pooling, and L2 normalization. Pooling accumulates in float32. Vectors have 384 dimensions. FAISS uses exact `IndexFlatIP`; normalized inner product is cosine similarity. High cosine scores can occur for irrelevant passages and do not establish factual correctness or answerability.

Passages have a 256-token ceiling including prefix and special tokens, with up to 32 tokens of overlap. Queries have a 512-token ceiling and are rejected rather than silently truncated. Actual prefixed text is re-encoded to verify budgets. Chunk boundaries come from the real tokenizer’s offsets into each existing parent source; they never cross parent page/section boundaries. Token boundaries can split words, including Arabic words in overlap regions; sentence-aware boundaries are a future refinement to evaluate.

Each chunk retains its parent source ID and exact Python Unicode character offsets into normalized document text. Browser highlighting uses Unicode codepoints, avoiding UTF-16 offset errors around emoji. Links carry document, source, start, and end parameters and are revalidated against the current document. Existing six demo documents and 28 parent sources retain their identities. Their encoder snapshot contains 29 chunks. No primary database migration was needed beyond the existing schema 3.

BM25 over encoder chunks uses the same lexical analyzer and k1=1.2 / b=0.75 as the original baseline. Compare BM25 and dense on this shared corpus to isolate retrieval differences; the original baseline has different passage boundaries.

## Resource and persistence behavior

- No model imports or downloads at API startup. Runtime inference makes no external network requests; ONNX Runtime telemetry is disabled.
- One embedding operation at a time per API process, using short-lived subprocesses and two CPU threads. Run one API worker on this machine.
- Require at least 1,024 MiB available RAM before starting; enforce a 768 MiB worker allocation cap through Windows Job Objects. This admission check cannot reserve system RAM or prevent other apps from consuming it afterward.
- Build timeout: 300 seconds. Query timeout: 30 seconds. Workers exit after each operation; shutdown cancels the active worker. A parent-process watcher prevents orphan inference workers.
- Build limits: 1,000,000 total parent characters, 5,000 parent sources, 10,000 chunks. These are intentionally smaller than the complete Library’s potential capacity.
- Optional packages: NumPy, ONNX Runtime, tokenizers, FAISS CPU. Both direct inputs and a tested lock are recorded separately from the base API environment.

Immutable UUID generation folders contain `index.faiss`, `chunks.sqlite3`, and `manifest.json`. The manifest records source revision/fingerprint, model/tokenizer hashes, encoder/chunker/analyzer versions, corpus hash, package versions, and actual build diagnostics. An atomic `current.json` pointer publishes a completed snapshot. Artifacts are hash-verified before loading; failed builds retain the previous pointer. Publication retires older managed snapshots using constrained, nonrecursive cache cleanup.

Uploads, replacement, and deletion invalidate the encoder snapshot. Revision and source-ID fingerprint checks also detect a database restore that reuses a revision with different sources. Requests fence source changes both before retrieval and while resolving results; stale/deleted source vectors are not returned. Rebuild is explicit to avoid expensive hidden inference. This is application-level integrity protection, not a security boundary against a user who can rewrite local code and artifacts. SQLite deletion is not a secure-erasure guarantee.

## Reproduce

With the base environment installed, from the project root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-ml-lock.txt
.\.venv\Scripts\python.exe scripts\prepare_embedding_model.py
```

The preparation script downloads only pinned files from the official model repository, validates sizes and hashes, and publishes each file atomically. It reuses valid files and refuses corrupt existing files. Start the API/frontend using the README commands, load the fictional pack, and choose **Build encoder index**. Keep at least 1 GiB system RAM available when running semantic searches.

Optional small inference/resource diagnostic:

```powershell
.\.venv\Scripts\python.exe scripts\check_embedding_runtime.py
```

Its four inputs exercise English/Arabic encoding. The generated report is ignored under `reports/generated/`; it is not a quality evaluation. API snapshot manifests also contain actual build-resource diagnostics.

## API

- `GET /api/retrieval/dense/status`: runtime/resources, snapshot provenance, current job, and last error.
- `POST /api/retrieval/dense/build`: starts an explicit background build (202).
- `POST /api/retrieval/search`: accepts `method: "bm25" | "dense"`, `corpus: "source" | "encoder"`, query, and top_k. Omitting method/corpus preserves the original BM25 API. Dense defaults to encoder corpus; dense/source is invalid.
- Encoder results add chunk ID, token count, corpus hash, exact source offsets, and optional worker diagnostics. HTTP 409 covers stale/corrupt snapshots; 503 covers missing runtime, busy workers, or insufficient RAM; 413 covers build size limits; 422 covers invalid queries/configurations.

## Verification and limits

The isolated environment passes 106 backend tests, the strict TypeScript/Vite build, and `pip check`. One upstream Starlette/AnyIO deprecation warning remains. Tests cover real tokenizer offsets, padding-aware pooling, L2 norms, independent inner-product checks, same-corpus BM25, persistence, failed build rollback, cache replacement, artifact corruption, revision/fingerprint fencing, deletion/replacement, resource rejection, and shutdown. Fast lifecycle tests intentionally use synthetic vectors; these cannot measure semantic quality.

A real model build indexed the six demo documents / 28 parent sources into 29 chunks. The build worker took about 3.44 seconds and peaked at 514.26 MiB resident RAM on one observed run. This timing excludes download/setup and is not a benchmark distribution. A live Egyptian Arabic query retrieved the shipping passage first, and the browser showed its exact full source highlight. Other returned passages included irrelevant policies; no confidence claim is attached to these rankings. Generated diagnostic reports are local observations, not held-out experiments or evaluation scores.

Live API checks also verified English retrieval, exact source slices for every returned hit, matching BM25/dense corpus hashes, stale-index rejection after a disposable upload, and rebuilding after deletion. The probe was removed; all original document/source content and identities matched the pre-test SHA256 digest. Only one managed snapshot remained. A forced API process restart retained the snapshot and successfully served another Arabic dense query without rebuilding. Browser checks at 390×844 and 1440×1050 found no horizontal page overflow; the source bookmark retained its exact highlight on reload. No browser console errors were observed in the final check. A preview was saved outside the repository.

## Next action

Phase 2e: add Reciprocal Rank Fusion over BM25 and dense retrieval on the shared encoder corpus, retain individual ranks/provenance, and validate deterministic fusion and stale-index handling. Reranking remains optional pending resource measurements. The reviewed retrieval/generation benchmark belongs to Phase 5; no test-set tuning or invented scores.
