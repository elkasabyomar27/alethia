import snapshot from './demo.json'

export interface Citation { sourceId: string; quote: string }
export interface SavedExample {
  id: string; language: string; label: string; question: string; status: string
  claims: { text: string; evidence: Citation[] }[]; model: string; savedAt: string
}
export interface Section { id: string; title: string; text: string }
export interface DemoDocument { id: string; filename: string; sections: Section[] }
export interface Metrics { recall_at_5: number; precision_at_5: number; mrr_at_10: number; ndcg_at_5: number }
interface Result { query_count: number; scored_count: number; metrics: Metrics | null; latency_median_ms: number | null; latency_p95_ms: number | null }
interface Pilot {
  runId: string; completedAt: string; corpusHash: string; datasetFingerprint: string
  samples: number; answerable: number; groups: number; languages: Record<string, number>
  summary: Record<string, Result & { languages: Record<string, Result> }>; limitations: string[]
  failures: { question: string; method: string; recall: number }[]
}
interface Demo { schema: number; documents: DemoDocument[]; examples: SavedExample[]; pilot: Pilot }

// No fetch, localStorage or mutation methods. Local runtime code is a different entry.
function freeze<T>(value: T): T {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.values(value).forEach(freeze)
    Object.freeze(value)
  }
  return value
}
const data: Demo = freeze(snapshot)
export const portfolioData = Object.freeze({
  examples: (): readonly SavedExample[] => data.examples,
  documents: (): readonly DemoDocument[] => data.documents,
  pilot: (): Pilot => data.pilot,
  source: (id: string): Section | undefined => data.documents.flatMap(d => d.sections).find(s => s.id === id),
})
export const evidenceLink = (id: string) => `#library?source=${encodeURIComponent(id)}`
