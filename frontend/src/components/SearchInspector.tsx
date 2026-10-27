import { useEffect, useRef, useState } from 'react'
import { getRetrievalStatus, searchKnowledge, type DenseStatus, type RetrievalStatus, type SearchResponse } from '../services/api'
import { sourceLink, type SourceRange } from '../services/sourceLinks'
import DensePanel from './DensePanel'

export default function SearchInspector({ libraryRevision, onInspectSource }: {
  libraryRevision: number
  onInspectSource: (documentId: string, sourceId: string, range?: SourceRange) => void
}) {
  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(5)
  const [status, setStatus] = useState<RetrievalStatus | null>(null)
  const [statusError, setStatusError] = useState('')
  const [result, setResult] = useState<SearchResponse | null>(null)
  const [error, setError] = useState('')
  const [searching, setSearching] = useState(false)
  const [mode, setMode] = useState<'legacy' | 'encoder' | 'dense' | 'hybrid'>('legacy')
  const [dense, setDense] = useState<DenseStatus | null>(null)
  const [denseRefresh, setDenseRefresh] = useState(0)
  const inFlight = useRef<AbortController | null>(null)
  const epoch = useRef(0)

  useEffect(() => {
    const controller = new AbortController()
    let live = true
    epoch.current += 1
    inFlight.current?.abort()
    setSearching(false)
    setResult(null)
    setError('')
    setStatus(null)
    setStatusError('')
    getRetrievalStatus(controller.signal).then((response) => { if (live) setStatus(response) })
      .catch((reason) => { if (live) setStatusError(reason instanceof Error ? reason.message : 'The search index is unavailable.') })
    return () => { live = false; controller.abort(); epoch.current += 1; inFlight.current?.abort() }
  }, [libraryRevision, mode])

  async function submitSearch() {
    const current = ++epoch.current
    inFlight.current?.abort()
    const controller = new AbortController()
    inFlight.current = controller
    setSearching(true)
    setResult(null)
    setError('')
    try {
      const response = await searchKnowledge(query.trim(), topK, controller.signal, mode)
      if (current !== epoch.current) return
      setResult(response)
      setStatus(response.index)
      setStatusError('')
    } catch (reason) {
      if (current === epoch.current) {
        setError(reason instanceof Error ? reason.message : 'Search failed. Please retry.')
        setDenseRefresh((value) => value + 1)
      }
    } finally {
      if (current === epoch.current) setSearching(false)
    }
  }

  const configuration = result?.index ?? (mode === 'legacy' ? status : null)
  return (
    <section className="search-inspector" aria-labelledby="search-heading">
      <div className="search-heading"><div><p className="eyebrow text-gold">FOLLOW THE EVIDENCE</p><h3 id="search-heading">Search Athena’s Library</h3></div><span className="search-method">{mode === 'hybrid' ? 'HYBRID · BM25 + SEMANTIC' : mode === 'dense' ? 'SEMANTIC · E5 / FAISS' : 'KEYWORD SEARCH · BM25'}</span></div>
      <p className="search-description">Retrieve evidence from English and Arabic documents. Keyword search matches words; semantic search uses local embeddings; hybrid search combines their ranks. Retrieved passages can still be irrelevant. Use The Oracle for answer drafts after configuring a generation provider.</p>
      <p className="encoder-summary" role="status">{dense?.state === 'ready' ? 'Semantic index ready' : dense?.state === 'stale' ? 'Semantic index needs rebuilding' : dense?.state === 'building' ? 'Semantic index is building' : 'Semantic index setup may be required'} · expand index tools for details.</p>
      <details className="index-tools"><summary>Semantic index & advanced tools</summary><DensePanel revision={`${libraryRevision}:${mode}:${denseRefresh}`} onStatus={setDense} /></details>
      <label className="retrieval-mode" htmlFor="retrieval-mode">Retrieval method<select id="retrieval-mode" value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}><option value="legacy">BM25 · original source baseline</option><option value="encoder" disabled={dense?.state !== 'ready'}>BM25 · encoder-aware chunks</option><option value="dense" disabled={dense?.state !== 'ready' || !dense.runtime_available}>Semantic · E5 / FAISS (same chunks)</option><option value="hybrid" disabled={dense?.state !== 'ready' || !dense.runtime_available}>Hybrid · BM25 + semantic (RRF)</option></select></label>
      <form className="search-form" onSubmit={(event) => { event.preventDefault(); if (query.trim()) void submitSearch() }}>
        <label htmlFor="knowledge-query">Question or search phrase</label>
        <div className="search-controls"><input id="knowledge-query" dir="auto" type="search" maxLength={500} required value={query} onChange={(event) => setQuery(event.target.value)} placeholder="What is the return policy? / سياسة الإرجاع" /><label className="search-limit" htmlFor="search-limit">Results<select id="search-limit" value={topK} onChange={(event) => setTopK(Number(event.target.value))}><option value={3}>3</option><option value={5}>5</option><option value={10}>10</option></select></label><button className="gold-button" type="submit" disabled={searching || !query.trim() || !status}>{searching ? 'Searching…' : 'Search knowledge'}</button></div>
      </form>
      <div className="search-index-status" role="status">{status ? `${status.indexed_documents} documents · ${status.indexed_segments} ${status.corpus === 'encoder' ? 'encoder chunks' : 'original source segments'} indexed${status.state === 'empty' ? ' · No searchable words yet' : ''}` : statusError || 'Checking the local keyword index…'}</div>
      {configuration && <details className="search-configuration"><summary>Search configuration</summary><dl><dt>Retriever</dt><dd>{configuration.retriever_version}</dd><dt>Analyzer</dt><dd>{configuration.analyzer_version}</dd><dt>SQLite</dt><dd>{configuration.sqlite_version}</dd><dt>Scoring</dt><dd>{configuration.method === 'hybrid' ? 'Equal-weight Reciprocal Rank Fusion · raw BM25 and cosine scores are not added' : configuration.method === 'dense' ? `Normalized inner product / cosine · ${configuration.dimension} dimensions` : `k1 = ${configuration.k1}, b = ${configuration.b}; any query term can match`}</dd><dt>Source segmentation</dt><dd>{configuration.chunking}</dd><dt>Index revision</dt><dd>{configuration.index_revision}</dd>{configuration.corpus_hash && <><dt>Shared chunk corpus</dt><dd>{configuration.corpus_hash}</dd></>}{configuration.fusion && <><dt>Fusion parameters</dt><dd>Rank constant {configuration.fusion.rank_constant} · up to {configuration.fusion.candidate_depth} candidates per retriever, independent of displayed result count · weights BM25 {configuration.fusion.weights.bm25}, semantic {configuration.fusion.weights.dense}</dd><dt>Actual candidate counts</dt><dd>BM25 {configuration.fusion.candidate_counts.bm25} · semantic {configuration.fusion.candidate_counts.dense}</dd></>}</dl><p>No reviewed retrieval-quality benchmark has been run. Compare hybrid, dense, and BM25 on encoder chunks; the original source baseline has different boundaries.</p></details>}
      {error && <p className="library-error" role="alert">{error}</p>}
      {result && <div className="search-results" aria-label="Retrieved passages">
        <div className="search-results-heading"><h4>Results for <bdi>{result.query}</bdi></h4><span>{result.hits.length} passages · {result.latency_ms.toFixed(1)} ms server search</span></div>
        <p className="search-score-note">{result.index.score_meaning} Scores do not establish answerability.</p>
        {result.index.method !== 'dense' && <details className="search-terms"><summary>Normalized lexical query terms</summary><p dir="auto">{result.normalized_terms.join(' · ')}</p></details>}
        {result.hits.length === 0 && <p className="search-no-results" role="status">No matching passages were found. Try words from your documents, or add a relevant source to the library. This does not establish whether the question is answerable.</p>}
        <ol>{result.hits.map((hit) => {
          const range = hit.chunk_id ? { start: hit.start_char, end: hit.end_char } : undefined
          return <li key={hit.chunk_id ?? hit.id} className="search-hit"><div className="search-hit-heading"><span className="search-rank" aria-label={`Rank ${hit.rank}`}>{String(hit.rank).padStart(2, '0')}</span><div><h4 dir="auto">{hit.filename}</h4><p dir="auto">{hit.section}</p></div><span className="search-score">{result.index.method === 'hybrid' ? 'RRF' : result.index.method === 'dense' ? 'Cosine' : 'BM25'} {hit.score.toPrecision(4)}</span></div><p className="search-excerpt" dir="auto">{Array.from(hit.text).slice(0, 280).join('')}{Array.from(hit.text).length > 280 ? '…' : ''}</p>{hit.retrievers && <details className="fusion-evidence"><summary>Why this passage ranked here</summary><dl>{(['bm25', 'dense'] as const).map((name) => {
            const component = hit.retrievers?.[name]
            return <div key={name}><dt>{name === 'bm25' ? 'BM25' : 'Semantic'}</dt><dd>{component ? `Rank ${component.rank} · raw ${name === 'bm25' ? 'BM25' : 'cosine'} ${component.score.toPrecision(5)} · RRF contribution ${component.contribution.toPrecision(6)}` : 'Outside the candidate list · contributes 0'}</dd></div>
          })}</dl><p>Only candidate ranks contribute to the RRF score. A missing candidate does not prove that evidence is absent.</p></details>}<div className="search-hit-footer"><span>{hit.source_label ?? `Lines ${hit.start_line}–${hit.end_line}`} · Document v{hit.revision}{hit.token_count != null ? ` · ${hit.token_count} tokens` : ''}</span><a className="quiet-button" href={sourceLink(hit.document_id, hit.id, range)} onClick={() => onInspectSource(hit.document_id, hit.id, range)}>Inspect source <span aria-hidden="true">→</span></a></div>{hit.warnings.length > 0 && <p className="search-extraction-note">This document has extraction notes. Review them in the source inspector.</p>}</li>
        })}</ol>
      </div>}
    </section>
  )
}
