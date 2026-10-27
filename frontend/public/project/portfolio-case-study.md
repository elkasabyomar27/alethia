# ALETHIA — Where Knowledge Becomes Answers

## The problem

Small businesses often spread support policies across documents. Finding the right passage takes time, and fluent AI answers can invent details. ALETHIA explores a support workflow that pairs answer drafts with inspectable evidence and a clear local handoff path.

## The product

Four Greek-inspired workspaces form one application: **Athena's Library** for documents and retrieval, **The Oracle** for English/Arabic answer drafts, **Hermes' Dispatch** for local review tickets, and **Themis' Tribunal** for review and evaluation. Classical engravings, bronze accents, restrained scroll motion, and responsive reading layouts provide the visual identity. Source credits are included with the locally stored artwork.

## Engineering choices

- React/TypeScript/Vite frontend and FastAPI/Pydantic backend, with SQLite persistence.
- Bounded PDF/DOCX parsing in isolated workers; TXT/Markdown normalization; stable document/source identities and revision-aware links.
- SQLite FTS5 BM25 baseline, pinned multilingual E5-small INT8 CPU embeddings, FAISS search, and reciprocal rank fusion over a shared encoder corpus. Reranking remains unimplemented.
- Small local inference was explored, but the user's 8 GB RAM machine motivated an explicit move to Gemini generation. An Ollama adapter remains available. The current default therefore requires a cloud API and is not fully offline.
- Generation, retrieval, persistence, and ticket management are separate. Document text is untrusted. Quote/citation checks and conservative escalation reduce particular failure modes but do not establish factual correctness or eliminate prompt injection.
- A 150-question candidate pack groups English, Modern Standard Arabic, and Egyptian Arabic variants into intent groups. Development and reserved groups are separated. Human review, final freeze, and quality evaluation remain unfinished.

## Evidence available today

The project has functional ingestion, retrieval, saved bilingual examples, source navigation, local tickets, reproducible retrieval diagnostics, and report exports. The Phase 6 verification record contains the observed test results and frontend build size. Diagnostic latency reports retain their run configuration and corpus identity.

No business ROI, accuracy improvement, hallucination rate, comparative retrieval gain, or generation-quality score has been established. Candidate count is not reviewed-dataset size. Historical screenshots demonstrate workflows, not general model performance.

## Tradeoffs and lessons

Memory admission checks and short-lived embedding workers favour a usable constrained laptop over maximal throughput. This adds model startup cost to semantic queries. A cloud generation adapter reduces local RAM demand but introduces connectivity, quota, privacy, and possible billing considerations. The frontend discloses what leaves the machine.

An explicit local ticket workflow makes uncertainty actionable without pretending to contact a human service. Evidence cards encourage inspection, while Themis deliberately leaves metrics blank when labels have not been reviewed. Long trace lists are rendered incrementally to reduce initial DOM work; full report exports remain available.

## Next validation gate

Personally review development references and complete relevance labels, arrange separate reserved-test review, freeze the dataset, and run fair retrieval comparisons. Then evaluate generation correctness, faithfulness, citation coverage, abstention, and handoff performance with transparent human grading. Until then, present ALETHIA as a polished engineering portfolio prototype with evaluation infrastructure, not a validated production support service.
