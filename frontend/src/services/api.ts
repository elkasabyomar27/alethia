export type BackendState = 'checking' | 'online' | 'offline'

export interface DocumentMetadata {
  id: string
  filename: string
  format: 'txt' | 'markdown' | 'pdf' | 'docx'
  content_hash: string
  size_bytes: number
  revision: number
  created_at: string
  updated_at: string
  processor_version: string
  character_count: number
  segment_count: number
  hash_basis: 'normalized_text' | 'original_file_bytes'
  page_count: number | null
  warnings: string[]
}

export interface SourceSegment {
  id: string
  document_id: string
  ordinal: number
  section: string
  text: string
  start_char: number
  end_char: number
  start_line: number
  end_line: number
  page_number: number | null
  source_label: string | null
}

export interface DocumentDetail extends DocumentMetadata {
  text: string
  segments: SourceSegment[]
}

export interface SaveResult {
  outcome: 'created' | 'duplicate' | 'updated'
  document: DocumentMetadata
}

export interface RetrievalStatus {
  state: 'ready' | 'empty'
  method: 'bm25' | 'dense' | 'hybrid'
  indexed_segments: number
  searchable_segments: number
  indexed_documents: number
  index_revision: number
  retriever_version: string
  analyzer_version: string
  built_at: string
  sqlite_version: string
  k1: number
  b: number
  chunking: string
  match_mode: 'any_term' | 'cosine' | 'rank_fusion'
  score_meaning: string
  corpus: 'source' | 'encoder'
  corpus_hash: string | null
  model_revision: string | null
  dimension: number | null
  fusion: { algorithm: 'rrf'; rank_constant: number; candidate_depth: number;
    weights: Record<string, number>; candidate_counts: Record<string, number> } | null
}

export interface SearchHit extends SourceSegment {
  rank: number
  filename: string
  format: DocumentMetadata['format']
  revision: number
  content_hash: string
  processor_version: string
  score: number
  matched_terms: string[]
  warnings: string[]
  chunk_id: string | null
  token_count: number | null
  retrievers: Record<'bm25' | 'dense', { rank: number; score: number; contribution: number } | null> | null
}

export interface SearchResponse {
  query: string
  normalized_terms: string[]
  top_k: number
  latency_ms: number
  index: RetrievalStatus
  hits: SearchHit[]
  worker_diagnostics: { elapsed_seconds: number; memory: { peak_rss_mib?: number; private_mib?: number } } | null
}

export interface DenseStatus {
  state: 'unavailable' | 'not_built' | 'building' | 'ready' | 'stale' | 'failed'
  runtime_available: boolean
  model_id: string
  model_revision: string
  dimension: number
  passage_token_limit: number
  worker_memory_limit_mib: number
  available_memory_mib: number
  current_source_revision: number
  last_error: string | null
  job: { state: string; stage: string; completed: number; total: number } | null
  snapshot: { chunk_count: number; source_count: number; source_revision: number; corpus_hash: string;
    chunker_version: string; built_at: string; build_diagnostics: { elapsed_seconds: number; memory: { peak_rss_mib?: number; private_mib?: number } } } | null
}

export interface OracleStatus {
  runtime: { state: 'ready' | 'configured' | 'key_missing' | 'model_missing' | 'model_mismatch' | 'offline'; model: string;
    provider: 'gemini' | 'ollama'; connection_verified?: boolean;
    digest?: string | null; runtime_version?: string; detail?: string }
  retrieval: DenseStatus['state']
  busy: boolean
  available_ram_mib: number
  context_tokens: number | null
  prompt_budget_bytes: number
  output_tokens: number
  prompt_version: string
  quality_evaluated: boolean
}

export interface OracleAnswer {
  question: string
  status: 'answered' | 'needs_human' | 'needs_clarification'
  reason: string | null
  claims: { text: string; evidence: { source_id: string; quote: string }[] }[]
  sources: { source_id: string; document_id: string; id: string; chunk_id: string; filename: string;
    section: string; revision: number; start_char: number; end_char: number; text: string; citation_state: 'current' | 'changed' | 'deleted' }[]
  latency_ms: number
  model: string
  model_digest: string | null
  provider: string | null
  model_version: string | null
  prompt_version: string
  corpus_hash: string | null
  context_version: string
  conversation_id: string
  conversation_revision: number
  turn_id: string
  created_at: string
  ticket_id?: string | null
  prompt_budget_bytes: number
  generation_diagnostics: { prompt_eval_count?: number; eval_count?: number; total_duration?: number; load_duration?: number } | null
}

export interface ConversationMetadata {
  id: string; title: string; created_at: string; updated_at: string; revision: number; turn_count: number
}
export interface ConversationDetail extends ConversationMetadata { turns: OracleAnswer[] }

export type TicketStatus = 'open' | 'in_progress' | 'resolved'
export interface TicketSummary {
  id: string; conversation_id: string; turn_id: string; question: string; reason: string;
  status: TicketStatus; revision: number; created_at: string; updated_at: string; resolution: string
}
export interface TicketDetail extends TicketSummary {
  snapshot: OracleAnswer; origin_available: boolean;
  events: { id: string; ticket_id: string; revision: number; kind: string; status: TicketStatus; note: string; created_at: string }[]
}

export interface EvaluationExample {
  id: string; group_id: string; split: 'dev' | 'test'; question: string; language: 'en' | 'ar_msa' | 'ar_egy';
  category: 'factual' | 'paraphrase' | 'multi_document' | 'unanswerable' | 'ambiguous'; reference_answer: string;
  answerable: boolean; evidence: { document: string; quote: string; grade: number }[]
}
export interface EvaluationReview {
  example: EvaluationExample; revision: number; review_status: 'unreviewed' | 'draft' | 'reviewed' | 'stale';
  reviewer: string; reviewed_at: string | null
}
export interface EvaluationDataset {
  dataset_id: string; corpus_fingerprint: string; candidate_count: number; candidate_pack_fingerprint: string;
  target_reviewed_questions: number; heldout_count: number; examples: EvaluationReview[]
}
export interface EvaluationMetrics { recall_at_5: number; precision_at_5: number; mrr_at_10: number; ndcg_at_5: number }
export interface EvaluationPreflight {
  dataset_id: string; candidate_count: number; development_count: number; reserved_test_count: number; groups: number; checked_at: string;
  encoder_generation: string | null; invalid_count: number; single_script_label_count: number; warning: string | null;
  languages: Record<string, number>; categories: Record<string, number>; reviews: Record<string, number>;
  limitations: string[]; results: { example_id: string; status: string; label_count: number; positive_chunk_count: number | null; error: string | null; review_notes: string[] }[]
}
export interface EvaluationSummary {
  query_count: number; scored_count: number; metrics: EvaluationMetrics | null; latency_median_ms: number | null; latency_p95_ms: number | null;
  languages?: Record<string, EvaluationSummary>
}
export interface EvaluationRun {
  id: string; status: 'running' | 'complete' | 'failed' | 'interrupted'; created_at: string; completed: number; total: number;
  summary: Record<string, EvaluationSummary> | null; error: string | null
}
export interface EvaluationReport {
  schema: number; run_id: string; mode: string; split: string; dataset_id: string; dataset_fingerprint: string;
  corpus_fingerprint: string; encoder_snapshot: { corpus_hash: string; model_id: string; model_revision: string };
  summary: Record<string, EvaluationSummary>; configurations: Record<string, unknown>; limitations: string[];
  results: { example_id: string; language: string; category: string; method: string; question: string; reference_answer: string;
    review_status: string; metrics: EvaluationMetrics | null; latency_ms: number;
    hits: { chunk_id: string; source_id: string; document_id: string; filename: string; section: string; start_char: number; end_char: number; excerpt: string; score: number }[] }[]
}

async function request<T>(path: string, options: RequestInit = {}, timeoutMs = 15_000): Promise<T> {
  const controller = new AbortController()
  const cancel = () => controller.abort()
  if (options.signal?.aborted) controller.abort()
  options.signal?.addEventListener('abort', cancel, { once: true })
  const timeout = window.setTimeout(cancel, timeoutMs)
  try {
    const response = await fetch(`/api${path}`, { ...options, signal: controller.signal })
    if (!response.ok) {
      const error: unknown = await response.json().catch(() => null)
      const detail = typeof error === 'object' && error !== null && 'detail' in error && typeof error.detail === 'string'
        ? error.detail : `Request failed (${response.status}). Please retry.`
      throw new Error(detail)
    }
    if (response.status === 204) return undefined as T
    return await response.json() as T
  } catch (error) {
    if (error instanceof TypeError || (error instanceof DOMException && error.name === 'AbortError')) {
      throw new Error('The local API could not be reached in time. Check the connection and retry.')
    }
    throw error
  } finally {
    window.clearTimeout(timeout)
    options.signal?.removeEventListener('abort', cancel)
  }
}

export const listDocuments = (signal: AbortSignal) => request<DocumentMetadata[]>('/documents', { signal })
export const getDocument = (id: string, signal: AbortSignal) => request<DocumentDetail>(`/documents/${encodeURIComponent(id)}`, { signal })
export const importDemoPack = () => request<SaveResult[]>('/demo/import', { method: 'POST' })
export const removeDocument = (id: string) => request<void>(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' })
export const getRetrievalStatus = (signal: AbortSignal) => request<RetrievalStatus>('/retrieval/status', { signal })
export const getDenseStatus = (signal: AbortSignal) => request<DenseStatus>('/retrieval/dense/status', { signal })
export const buildDenseIndex = () => request<DenseStatus>('/retrieval/dense/build', { method: 'POST' })
export const getOracleStatus = (signal: AbortSignal) => request<OracleStatus>('/oracle/status', { signal })
export const askOracle = (question: string, conversationId?: string, revision?: number) => request<OracleAnswer>('/oracle/ask', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question,
    conversation_id: conversationId, expected_revision: revision }),
}, 165_000)
export const listConversations = (signal: AbortSignal) => request<ConversationMetadata[]>('/oracle/conversations', { signal })
export const getConversation = (id: string, signal: AbortSignal) => request<ConversationDetail>(`/oracle/conversations/${encodeURIComponent(id)}`, { signal })
export const deleteConversation = (id: string) => request<void>(`/oracle/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })
export const listTickets = (status: TicketStatus | 'all', signal: AbortSignal) => request<TicketSummary[]>(`/tickets${status === 'all' ? '' : `?status=${status}`}`, { signal })
export const getTicket = (id: string, signal: AbortSignal) => request<TicketDetail>(`/tickets/${encodeURIComponent(id)}`, { signal })
export const createTicket = (conversationId: string, turnId: string) => request<{ outcome: 'created' | 'existing'; ticket: TicketDetail }>('/tickets', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ conversation_id: conversationId, turn_id: turnId }),
})
export const updateTicket = (id: string, revision: number, status: TicketStatus, note: string) => request<TicketDetail>(`/tickets/${encodeURIComponent(id)}`, {
  method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_revision: revision, status, note }),
})
export const deleteTicket = (id: string, revision: number) => request<void>(`/tickets/${encodeURIComponent(id)}?expected_revision=${revision}`, { method: 'DELETE' })
export const getEvaluationDataset = (signal: AbortSignal) => request<EvaluationDataset>('/evaluation/dataset', { signal })
export const getEvaluationPreflight = () => request<EvaluationPreflight>('/evaluation/preflight')
export const getEvaluationRuns = (signal: AbortSignal) => request<EvaluationRun[]>('/evaluation/runs', { signal })
export const getEvaluationReport = (id: string, signal: AbortSignal) => request<EvaluationReport>(`/evaluation/runs/${encodeURIComponent(id)}`, { signal })
export const saveEvaluationReview = (review: EvaluationReview, approve: boolean, reviewer: string) => request<EvaluationReview>(`/evaluation/reviews/${encodeURIComponent(review.example.id)}`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ example: review.example, expected_revision: review.revision, approve, reviewer }),
})
export const inspectEvaluationEvidence = (example: EvaluationExample) => request<{ document: string; document_id: string; source_id: string; quote: string; start_char: number; end_char: number }[]>('/evaluation/evidence', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(example),
})
export const startEvaluationRun = (methods: string[], reviewedOnly: boolean) => request<EvaluationRun>('/evaluation/runs', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ methods, reviewed_only: reviewedOnly }),
})
export const searchKnowledge = (query: string, topK: number, signal: AbortSignal, mode: 'legacy' | 'encoder' | 'dense' | 'hybrid' = 'legacy') => request<SearchResponse>('/retrieval/search', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query, top_k: topK,
    method: mode === 'dense' || mode === 'hybrid' ? mode : 'bm25', corpus: mode === 'legacy' ? 'source' : 'encoder' }), signal,
}, mode === 'dense' || mode === 'hybrid' ? 45_000 : 15_000)
export function saveDocument(file: File, replaceId?: string) {
  const path = replaceId ? `/documents/${encodeURIComponent(replaceId)}` : '/documents'
  return request<SaveResult>(`${path}?${new URLSearchParams({ filename: file.name })}`, {
    method: replaceId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file,
  })
}

export async function checkBackend(signal: AbortSignal): Promise<void> {
  const response = await fetch('/api/health', { signal })
  if (!response.ok) throw new Error('Backend unavailable')
  const health: unknown = await response.json()
  if (typeof health !== 'object' || health === null || !('status' in health) || health.status !== 'ok') {
    throw new Error('Unexpected health response')
  }
}
