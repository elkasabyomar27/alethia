# Phase 1 · Foundation

## Inspected environment · 2026-10-26

The Alethia project directory was empty before implementation. No applicable ancestor AGENTS.md was found in the inspected workspace ancestry.

| Item | Observed |
| --- | --- |
| OS | Windows; PowerShell |
| Python | 3.11.0 |
| Node / npm | 24.15.0 / 11.12.1 |
| Git | 2.52.0.windows.1; no project repository |
| GPU | NVIDIA RTX 2050, 4096 MiB VRAM, driver 566.07 (nvidia-smi) |
| RAM | 7.82 GiB total; about 1.00 GiB available at inspection |
| C: free space | About 24.1 GiB at inspection |
| Ollama | Not on PATH or found at two common install locations; inference unverified |
| Existing Python packages | FastAPI 0.121.0, Pydantic 2.12.3, Uvicorn 0.52.1, pytest 9.1.1, torch 2.9.0, sentence-transformers 5.5.0, faiss-cpu 1.13.0 |

Package metadata confirms installation, not successful model execution, CUDA support, or end-to-end compatibility. CIM queries were unavailable in the sandbox; RAM was read through the Windows memory API and GPU information through nvidia-smi. Available memory is a transient measurement.

## Small implementation steps and acceptance criteria

1. **Inspect and bound resource use.** Record tools and model candidates. Download no weights or ML dependencies during Phase 1.
2. **Create a minimal backend.** `/api/health` returns validated liveness metadata; `/api/capabilities` accurately labels unbuilt features. API tests pass, including absence of simulated chat responses.
3. **Create the application shell.** React, Vite, TypeScript, Tailwind, and custom CSS; four hash-addressable module screens; local temple illustration; no external assets needed at runtime. Navigation supports keyboard use, visible focus, a skip link, narrow screens, and reduced motion settings.
4. **Connect and verify.** Frontend health check has a timeout, offline state, and retry. Vite proxies API requests to the loopback backend. TypeScript and production build pass; verify live API through Vite. Review desktop and mobile layout where a browser is available.
5. **Record handoff.** Setup instructions, concise checklist, test outcomes, and next action. No commits or pushes.

## Architecture decisions

- Keep one FastAPI process and one local frontend server. No containers, worker system, orchestration framework, or cloud services for the MVP.
- Use the same-origin `/api` path through Vite in development, avoiding broad CORS permissions. Production hosting is not yet configured.
- Keep retrieval and generation separate. Later model adapters load lazily; a responsive API must not imply that models are ready.
- Plan SQLite as the metadata source of truth, with stable document/chunk identifiers and versioned index rebuilds. Deletion and crash recovery must be tested before claiming persistent index reliability.
- Add directories as their implementations arrive. Do not scaffold empty RAG/evaluation/database packages or pretend that the benchmark exists.

## Local model candidates · provisional, not validated

**Generation:** [`qwen2.5:1.5b`](https://ollama.com/library/qwen2.5:1.5b), Q4_K_M, approximately 986 MB model artifact. The [upstream 1.5B instruct model](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct) declares Apache-2.0; Arabic is listed in the model family’s multilingual support. This makes it a trial candidate, not a guarantee of Arabic correctness or RAG reliability. Artifact size excludes runtime buffers, KV cache, and other memory. Begin trials with a 2,048-token context, one concurrent generation, and short output limits. Use the GPU for generation if verified; benchmark actual memory, latency, and quality before deciding. No 7B download on this machine as a starting point.

**Retrieval:** [`intfloat/multilingual-e5-small`](https://huggingface.co/intfloat/multilingual-e5-small?inference_provider=hf-inference), MIT, 384-dimensional embeddings, 512-token input ceiling, approximately 471 MB FP32 weight file. Use CPU encoding, small batches, normalized embeddings, and the required `query: ` / `passage: ` prefixes even for Arabic. Token-aware chunks must leave room for prefixes and avoid silent truncation. Index size for 10,000 float32 vectors is about 14.6 MiB before metadata/FAISS overhead; encoder/runtime RAM is additional. This is a capacity calculation, not a measured workload.

Node 24 satisfies the [Vite runtime requirement](https://vite.dev/guide/). Python package compatibility still needs an isolated dependency installation; the first shell checks may use the existing interpreter and must be labeled accordingly.

## Important risks and mitigation

| Risk | Planned response / evidence required |
| --- | --- |
| Only ~1 GiB RAM currently free | Keep Phase 1 model-free. Close heavy apps before inference trials; monitor total process memory and GPU memory. Avoid simultaneous model loading and large evaluations. |
| Windows GPU / native packages | Verify Ollama GPU offload and Python import compatibility separately. Existing torch installation does not prove CUDA usability. Check FAISS wheel availability before isolated install. |
| Small model limitations | Evaluate factuality, abstention, citation support, and English/MSA/Egyptian Arabic separately. Use short contexts; record failures, never promise model quality from parameter count. |
| Arabic retrieval mismatch | Preserve original text. Test Arabic normalization and a shared BM25 analyzer; keep English/Arabic mixed text. Dense cross-language retrieval and dialect quality require reviewed examples. |
| Unreliable similarity thresholds | Calibrate abstention on the development split. Similarity scores and valid citation IDs do not establish truth. |
| Prompt injection in uploads | Separate instructions from document data, delimit context, constrain source IDs, and evaluate adversarial documents. Prompt formatting alone is not a security guarantee. |
| PDF layout, scans, corrupt files | Validate size/type; bound extraction; preserve pages. Explicitly identify scanned/no-text PDFs; OCR is not in the initial ingestion scope. |
| Benchmark leakage and grading bias | Human-review evidence and references; freeze test split. Tune on development only; log configuration, revisions, corpus hash, sample counts, and uncertainty. |

Reranking remains an optional experiment after baseline memory measurements. A fair comparison must state when reranking is unavailable rather than insert placeholder results.

## Next milestone

Phase 2a: create the fictional e-commerce document pack, then implement bounded TXT/Markdown upload, SQLite metadata, stable source IDs, duplicate detection, and extraction/chunking tests. Extend to PDF/DOCX and retrieval incrementally within Phase 2. Human benchmark review remains outstanding; synthetic items must be marked unreviewed.
