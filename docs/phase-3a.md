# Phase 3a — The Oracle: initial local generation

## Delivered and boundaries

The Oracle now retrieves hybrid evidence, generates local answer drafts, validates citation IDs and exact supporting quotes, and links to the current source spans. English and Arabic examples ran on the development machine. A live stock request abstained. Ten recent turns remain in tab memory across module navigation, with a clear-session control; reload clears them. Each request is independent: prior turns are not passed to the model.

This is the first Phase 3 milestone, not a claim that generation quality or the complete phase is finished. Durable conversations, reliable follow-up resolution, adversarial validation, and the reviewed benchmark remain outstanding. Human-review messages do not create tickets or send messages; Hermes remains Phase 4.

## Inspected environment and pinned artifacts

At inspection, Ollama was absent from PATH, common install paths, and the local endpoint. The machine had about 1.3 GiB free RAM and 3.25 GiB free VRAM on its 4 GiB RTX 2050, with roughly 24 GiB free disk space. Existing documents/indexes were inspected before edits.

The provisional Qwen 1.5B choice was retained. The [official model listing](https://ollama.com/library/qwen2.5:1.5b) identifies Q4_K_M quantization and Apache-2.0 licensing; [upstream model metadata](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct) confirms the license. This makes it a free local candidate, not evidence of reliable Arabic/RAG quality.

| Artifact | Pinned identity / observed size |
| --- | --- |
| Official portable runtime | [Ollama v0.40.11 release](https://github.com/ollama/ollama/releases/tag/v0.40.11) |
| Windows AMD64 ZIP | 1,586,356,606 bytes; SHA256 `bda4a493ba8a7c24d57263cd843cd68cee84f44aed4299eeed532acad7eda12a` |
| Extracted runtime | 2,231,045,135 bytes observed locally |
| Model tag | `qwen2.5:1.5b` |
| Manifest SHA256 | `65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b` |
| GGUF model layer | 986,048,512 bytes; SHA256 `183715c435899236895da3869489cc30ac241476b4971a20285b1a462818a5b4` |
| Model plus manifest layers | 986,061,892 bytes reported by Ollama |

The runtime and weights are under ignored `models/`. The setup keeps the archive for reproducibility; no global PATH/startup entry or paid service was added. Ollama itself created its normal local identity key under the user’s `.ollama` directory at first start; the application does not read or publish it.

## Reproduction

Follow README base/encoder setup, then from the project root:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_ollama_runtime.py
.\scripts\start_ollama.ps1
```

Keep the server terminal open. In another terminal:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_qwen_model.py
```

The runtime preparer verifies the official archive’s pinned SHA256/size, checks at least 8 GiB free disk, bounds extraction, rejects unsafe archive paths, and publishes a staging directory only after the executable exists. It refuses an existing incomplete extraction instead of deleting work. The model preparer explicitly calls the local pull API, then verifies the full pinned manifest digest. Neither download runs during API startup or a question.

The start script binds `127.0.0.1:11434`, stores model blobs in `models/ollama`, disables Ollama cloud inference, and sets one parallel request/loaded model, queue size one, 4,096-token default context, and zero keep-alive. No cloud account is required. [Official Windows requirements](https://docs.ollama.com/windows) and [GPU documentation](https://docs.ollama.com/gpu) were consulted; the actual server detected CUDA compute capability 8.6 and its CUDA 12 library on the RTX 2050.

Start the API/frontend with README commands. Open The Oracle and refresh readiness. The API accepts only plain loopback HTTP origins and this pinned model; it bypasses environment HTTP proxies and does not follow redirects. Backend environment overrides must be exported before startup; `.env` is not automatically loaded.

## Request pipeline and resource controls

1. Inspect local runtime/model digest, check no model is already loaded, and require at least 1,536 MiB free NVIDIA VRAM.
2. Hybrid retrieval over the current shared encoder snapshot. Existing 1,024 MiB available-RAM admission and worker limits apply.
3. Let the embedding subprocess exit, then reserve the same dense admission guard for generation. Concurrent semantic searches/builds cannot overlap this application’s LLM operation. Original BM25 and document management remain available.
4. Select up to three ranked passages. Construct a bounded prompt with source IDs and the question placed after the evidence. The JSON output schema is explicitly included in the system prompt as well as sent to Ollama’s structured-output formatter.
5. Generate with `num_ctx=4096`, `num_predict=384`, temperature 0, seed 42, two CPU threads, GPU offload requested, and `keep_alive=0`.
6. Validate the output, recheck model/source identity, return only validated claims/source mappings, and explicitly unload the model.

The prompt uses a conservative UTF-8 byte budget for the pinned byte-BPE tokenizer, reserving output plus 256 tokens for template overhead. It counts serialized messages/schema, rejects oversized questions, and clips passage prefixes without silently increasing the context window. This underuses context, particularly Arabic. Clipping can end mid-word/sentence; better boundary selection and evidence coverage are next-milestone work. Returned offsets match the exact prefix provided to the model.

The HTTP adapter bounds response bytes (64 KiB for generation) and uses a 120-second socket timeout. This is not a strict process wall-clock limit or an OS memory cap for Ollama. Generation output is capped, only one request runs in this API process, and an incomplete output is rejected. Explicit unload has a separate 15-second timeout. If cleanup fails, the dense admission reservation remains held until a readiness refresh confirms Ollama is idle. Other applications or another API process are outside these guards; run one ALETHIA API worker.

Admission checks do not reserve system memory. Free RAM dipped below 1 GiB during one observed load. The external Ollama runner is not inside the encoder’s 768 MiB Job Object. An unavailable GPU, low RAM/VRAM, busy/loaded model, stale index, or local runtime failure produces an explicit error rather than simulated answers.

## Grounding contract and limitations

The model returns `status: answer | insufficient_evidence` and up to three claims. Every claim requires evidence entries containing an allowed source ID and a verbatim quote (12–600 characters) from that exact supplied context. Unknown IDs, empty claims, malformed JSON, invented quotes, or embedded citation markers with invalid structure withhold all generated claims. Model/source changes during generation reject the result. Source URLs and document metadata come from the backend, never from model-supplied URLs.

`needs_human` covers missing evidence, model abstention, invalid output, and invalid citations. It is not a calibrated confidence decision and does not imply that a ticket was created. The user-facing fallback uses a basic Arabic-script heuristic; this is not full language identification.

**A matching quote does not establish entailment, relevance, or completeness.** No local judge, similarity confidence threshold, or unsupported factual-quality score is used. Instructions separate source data from behavior, but prompt formatting and quote checks are not a proven defense against prompt injection. The UI labels answers as source-linked drafts and asks users to verify them.

## Development observations, including failures

All recorded runs are small development diagnostics, not held-out evaluation or human-reviewed benchmark items. Earlier reports are retained rather than overwritten:

| Prompt | Question/result observed | Server time |
| --- | --- | --- |
| v1 | General returns question: abstained despite relevant evidence | 6.80 s |
| v1 | Specific return-window question: also abstained | 5.41 s |
| v2 | Specific return-window question: gave an unrelated opened-product restriction, overgeneralized beyond the quoted named products | 5.79 s |
| v3 | Same specific English question: stated 14 calendar days and quoted that policy | 6.14 s |
| v3 | MSA return-window question: stated 14 calendar days plus the source’s unused/packaging conditions | 8.37 s |
| v3 | Live stock count: abstained without inventing a number | 5.98 s |

v1 omitted the schema from the model-visible prompt; v2 made it explicit. v2’s citation check still accepted an irrelevant/overgeneralized claim. v3 moved the question after the passages and added relevance/scope instructions. These development changes have not been validated broadly, and the v2 failure demonstrates why citation validity must not be labeled correctness. No final test split exists yet and no test-set tuning occurred.

Ollama reported a maximum sampled model VRAM allocation of 1,169,382,440 bytes (~1.09 GiB) during these requests. This is model-reported allocation, not a complete measurement of all CUDA/process overhead. Minimum sampled available RAM on the MSA run was about 985 MiB. Samples were taken every 0.5 seconds and can miss peaks. Prompt counts for final CLI samples were 787–825 tokens, well below the configured context. `/api/ps` was empty after each diagnostic, confirming unload in these runs.

To reproduce one functional/resource observation:

```powershell
.\.venv\Scripts\python.exe scripts\check_oracle_runtime.py --label english --question 'How many days after delivery can I request a change-of-mind return?'
```

Reports go to ignored `reports/generated/phase3a-*.json`. They can contain question/answer/source text; keep private diagnostics out of the public repository.

## Tests and next action

The final environment passes 146 backend tests and `pip check`; one existing Starlette/AnyIO deprecation warning remains. Tests use explicit fake model responses for contract checks, not fabricated model performance. They cover local-only HTTP/proxy/redirect handling, byte limits, malformed input, prompt budgets/Unicode, citation rejection, genuine dense-index admission, source/model changes, output withholding, cleanup failures, and recovery. The frontend builds with strict TypeScript.

Browser verification added an Egyptian Arabic question about the change-of-mind return window. It returned the source’s 14-day rule and conditions in Arabic (7.48 seconds observed server time). Its clickable citation highlighted the supporting passage, and session history survived navigation to the Library and back. Expanded supporting quotes/provenance worked at mobile 390×844 and desktop 1440×1050 sizes without horizontal page overflow. The final console error check was empty, and a screenshot was saved outside the repository. The original six documents / 28 sources retained their content/identity digest. Ollama was idle afterward. No commit or push was made.

Next: Phase 3b — strengthen evidence selection and sentence boundaries, add development cases for question coverage, product scope, ambiguity, follow-ups, and prompt injection, then add durable conversation history with revision-aware citations. Keep quality claims separate from these engineering checks; the reviewed 150-question evaluation remains Phase 5.
