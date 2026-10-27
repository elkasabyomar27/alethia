import { useEffect, useState } from 'react'
import { getEvaluationDataset, getEvaluationPreflight, getEvaluationReport, getEvaluationRuns, inspectEvaluationEvidence, saveEvaluationReview, startEvaluationRun,
  type EvaluationDataset, type EvaluationMetrics, type EvaluationPreflight, type EvaluationReport, type EvaluationReview, type EvaluationRun } from '../services/api'
import { sourceLink } from '../services/sourceLinks'

const metricKeys = ['recall_at_5', 'precision_at_5', 'mrr_at_10', 'ndcg_at_5'] as const
const metricLabels = ['Recall@5', 'Precision@5', 'MRR@10', 'nDCG@5']

export default function Tribunal() {
  const [dataset, setDataset] = useState<EvaluationDataset | null>(null)
  const [runs, setRuns] = useState<EvaluationRun[]>([])
  const [report, setReport] = useState<EvaluationReport | null>(null)
  const [selectedRun, setSelectedRun] = useState('')
  const [traceQuery, setTraceQuery] = useState('')
  const [traceLimit, setTraceLimit] = useState(20)
  const matchingTraces = report?.results.filter((item) => `${item.example_id} ${item.method} ${item.question}`.toLocaleLowerCase().includes(traceQuery.trim().toLocaleLowerCase())) ?? []
  useEffect(() => { setTraceQuery(''); setTraceLimit(20) }, [selectedRun])
  const [review, setReview] = useState<EvaluationReview | null>(null)
  const [reviewer, setReviewer] = useState('')
  const [attest, setAttest] = useState(false)
  const [methods, setMethods] = useState(['bm25'])
  const [reviewedOnly, setReviewedOnly] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [evidence, setEvidence] = useState<Awaited<ReturnType<typeof inspectEvaluationEvidence>>>([])
  const [languageFilter, setLanguageFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('needs-review')
  const [questionFilter, setQuestionFilter] = useState('')
  const [preflight, setPreflight] = useState<EvaluationPreflight | null>(null)
  const visibleCandidates = dataset?.examples.filter((item) =>
    (languageFilter === 'all' || item.example.language === languageFilter) &&
    (statusFilter === 'all' || (statusFilter === 'needs-review' ? item.review_status !== 'reviewed' : item.review_status === statusFilter)) &&
    `${item.example.id} ${item.example.group_id} ${item.example.question}`.toLocaleLowerCase().includes(questionFilter.trim().toLocaleLowerCase())) ?? []
  const pendingCandidates = visibleCandidates.filter((item) => item.review_status !== 'reviewed')
  const reviewedCount = dataset?.examples.filter((item) => item.review_status === 'reviewed').length ?? 0
  const active = runs.find((run) => run.status === 'running')

  useEffect(() => { setEvidence([]) }, [review?.example])

  useEffect(() => {
    setPreflight(null)
    const controller = new AbortController()
    getEvaluationDataset(controller.signal).then(setDataset).catch((reason) => { if (!controller.signal.aborted) setError(String(reason.message ?? reason)) })
    return () => controller.abort()
  }, [refresh])

  useEffect(() => {
    const controller = new AbortController()
    let timer: number | undefined
    const poll = async () => {
      try {
        const next = await getEvaluationRuns(controller.signal)
        if (controller.signal.aborted) return
        setRuns(next)
        if (next.some((run) => run.status === 'running')) timer = window.setTimeout(() => void poll(), 1000)
      } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Runs unavailable.') }
    }
    void poll()
    return () => { controller.abort(); window.clearTimeout(timer) }
  }, [refresh])

  useEffect(() => {
    setReport(null)
    if (!selectedRun) return
    const controller = new AbortController()
    getEvaluationReport(selectedRun, controller.signal).then((value) => { if (!controller.signal.aborted) setReport(value) })
      .catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Report unavailable.') })
    return () => controller.abort()
  }, [selectedRun])

  function selectReview(identity: string) {
    const row = dataset?.examples.find((item) => item.example.id === identity)
    setReview(row ? structuredClone(row) : null)
    setReviewer(row?.reviewer ?? '')
    setAttest(false)
    setEvidence([])
    setError('')
    setNotice('')
  }

  async function saveReview() {
    if (!review) return
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await saveEvaluationReview(review, attest, reviewer)
      setReview(result); setAttest(false); setRefresh((value) => value + 1)
      setNotice(result.review_status === 'reviewed' ? 'Personal review attestation recorded against the current library.' : 'Draft saved. This example is not approved for quality scoring.')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Review save failed.') }
    finally { setBusy(false) }
  }

  async function run() {
    setBusy(true); setError(''); setNotice('')
    try {
      await startEvaluationRun(methods, reviewedOnly)
      setRefresh((value) => value + 1)
      setNotice('Retrieval run started. No Gemini or answer-generation calls are made.')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Run could not start.') }
    finally { setBusy(false) }
  }

  async function inspectEvidence() {
    if (!review) return
    setBusy(true); setError(''); setEvidence([])
    try { setEvidence(await inspectEvaluationEvidence(review.example)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Evidence inspection failed.') }
    finally { setBusy(false) }
  }

  async function checkEvidence() {
    setBusy(true); setError(''); setPreflight(null)
    try { setPreflight(await getEvaluationPreflight()) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Preflight unavailable.') }
    finally { setBusy(false) }
  }

  function nextPending() {
    if (!pendingCandidates.length) return
    const index = pendingCandidates.findIndex((item) => item.example.id === review?.example.id)
    selectReview(pendingCandidates[(index + 1) % pendingCandidates.length].example.id)
  }

  const metric = (value: EvaluationMetrics | null, key: typeof metricKeys[number]) => value ? value[key].toFixed(4) : 'Awaiting review'
  return <section className="tribunal" aria-labelledby="themis-heading">
    <div className="oracle-heading"><div><p className="eyebrow text-gold">THEMIS’ TRIBUNAL · EVALUATION LABORATORY</p><h2 id="themis-heading">Evidence before a quality claim.</h2></div><span className="search-method">REPRODUCIBLE RETRIEVAL</span></div>
    <p className="oracle-guidance">Inspect questions and supporting evidence, record your own review, then run a controlled retrieval comparison. Unreviewed examples produce diagnostic traces and latency only. Correctness, faithfulness, generation, and handoff quality have not been evaluated here.</p>
    <div className="evaluation-summary"><div><strong>{dataset?.candidate_count ?? '—'}</strong><span>Total candidate questions</span></div><div><strong>{dataset?.examples.length ?? '—'}</strong><span>Development candidates</span></div><div><strong>{reviewedCount}</strong><span>Development review attestations</span></div><div><strong>{dataset?.heldout_count ?? '—'}</strong><span>Reserved test candidates · contents withheld</span></div></div>
    <p className="oracle-session-note">Target: approximately {dataset?.target_reviewed_questions ?? 150} human-reviewed questions. This candidate pack is agent-authored. Reserved test groups are hidden from development review and runs; the final reviewed benchmark is not frozen.</p>
    {error && <p className="library-error" role="alert">{error}</p>}
    {notice && <p className="evaluation-notice" role="status">{notice}</p>}
    <div className="evaluation-actions"><button className="quiet-button" disabled={busy} onClick={() => void checkEvidence()}>Check development evidence</button><a className="quiet-button" href="/api/evaluation/review-packet">Export development review packet</a></div>
    {preflight && <div className="evaluation-preflight" role="status"><h4>Structural evidence preflight</h4><p>{preflight.development_count} development candidates · {preflight.groups} intent groups · {preflight.invalid_count} invalid evidence mappings · {preflight.reserved_test_count} reserved test candidates excluded.</p><p>{Object.entries(preflight.languages).map(([language, count]) => `${language}: ${count}`).join(' · ')}</p><p>{Object.entries(preflight.categories).map(([category, count]) => `${category}: ${count}`).join(' · ')}</p><p>{preflight.single_script_label_count} cases have evidence labels in one script only. Check for equivalent passages in the other language; this is a review prompt, not a failed mapping.</p><p>{preflight.encoder_generation ? 'Document and encoder-chunk mappings checked.' : preflight.warning} Checked {new Date(preflight.checked_at).toLocaleString()}.</p><p>Quote resolution does not approve references, answerability, or label completeness. No model inference or quality scoring was performed.</p><details><summary>Inspect preflight results and limitations</summary><ul>{preflight.limitations.map((item) => <li key={item}>{item}</li>)}</ul>{preflight.results.map((item) => <p key={item.example_id}><strong>{item.example_id}</strong> · {item.status}{item.error ? ` · ${item.error}` : ''}{item.review_notes.map((note) => <span key={note}> · {note}</span>)}</p>)}</details></div>}
    <details className="evaluation-review"><summary>Review development questions and evidence</summary>
      <div className="evaluation-review-filters"><label>Question language<select value={languageFilter} disabled={busy} onChange={(event) => setLanguageFilter(event.target.value)}><option value="all">All languages</option><option value="en">English</option><option value="ar_msa">Modern Standard Arabic</option><option value="ar_egy">Egyptian Arabic</option></select></label><label>Review status<select value={statusFilter} disabled={busy} onChange={(event) => setStatusFilter(event.target.value)}><option value="needs-review">Needs review</option><option value="all">All statuses</option><option value="unreviewed">Unreviewed</option><option value="draft">Draft</option><option value="reviewed">Reviewed</option><option value="stale">Stale review</option></select></label><label>Find a candidate<input value={questionFilter} disabled={busy} maxLength={500} onChange={(event) => setQuestionFilter(event.target.value)} placeholder="Question, ID, or intent group" /></label></div>
      <p>{visibleCandidates.length} candidates match these filters. Filters leave the current editor unchanged; selecting another candidate discards unsaved edits.</p>
      <label htmlFor="evaluation-example">Candidate question<select id="evaluation-example" value={review?.example.id ?? ''} disabled={busy} onChange={(event) => selectReview(event.target.value)}><option value="">Select a candidate</option>{review && !visibleCandidates.some((item) => item.example.id === review.example.id) && <option value={review.example.id}>{review.example.id} · current selection outside filters</option>}{visibleCandidates.map((item) => <option key={item.example.id} value={item.example.id}>{item.example.id} · {item.example.language} · {item.review_status}</option>)}</select></label>
      <button className="quiet-button" disabled={busy || pendingCandidates.length === 0} onClick={nextPending}>Select next unreviewed candidate</button>
      {review && <div className="review-editor"><p>Group: {review.example.group_id} · development split · revision {review.revision}</p>
        <label htmlFor="review-question">Question<textarea id="review-question" dir="auto" maxLength={500} value={review.example.question} disabled={busy} onChange={(event) => setReview({ ...review, example: { ...review.example, question: event.target.value } })} /></label>
        <label htmlFor="review-answer">Reference answer / expected behavior<textarea id="review-answer" dir="auto" maxLength={2000} value={review.example.reference_answer} disabled={busy} onChange={(event) => setReview({ ...review, example: { ...review.example, reference_answer: event.target.value } })} /></label>
        <label className="evaluation-check"><input type="checkbox" checked={review.example.answerable} disabled={busy} onChange={(event) => setReview({ ...review, example: { ...review.example, answerable: event.target.checked, evidence: event.target.checked ? review.example.evidence : [] } })} />Answerable from the current knowledge base</label>
        {review.example.answerable && <><h4>Expected supporting evidence</h4>{review.example.evidence.map((label, index) => <div className="review-evidence" key={index}>
          <label>Document filename<input value={label.document} maxLength={180} disabled={busy} onChange={(event) => setReview({ ...review, example: { ...review.example, evidence: review.example.evidence.map((item, i) => i === index ? { ...item, document: event.target.value } : item) } })} /></label>
          <label>Exact quote<textarea dir="auto" value={label.quote} maxLength={1200} disabled={busy} onChange={(event) => setReview({ ...review, example: { ...review.example, evidence: review.example.evidence.map((item, i) => i === index ? { ...item, quote: event.target.value } : item) } })} /></label>
          <label>Relevance grade<select value={label.grade} disabled={busy} onChange={(event) => setReview({ ...review, example: { ...review.example, evidence: review.example.evidence.map((item, i) => i === index ? { ...item, grade: Number(event.target.value) } : item) } })}><option value={1}>1 · Relevant</option><option value={2}>2 · Strongly relevant</option><option value={3}>3 · Essential</option></select></label>
          <button className="quiet-button" disabled={busy} onClick={() => setReview({ ...review, example: { ...review.example, evidence: review.example.evidence.filter((_, i) => i !== index) } })}>Remove evidence</button>
        </div>)}<button className="quiet-button" disabled={busy || review.example.evidence.length >= 8} onClick={() => setReview({ ...review, example: { ...review.example, evidence: [...review.example.evidence, { document: '', quote: '', grade: 1 }] } })}>Add evidence</button></>}
        <div className="evaluation-actions"><button className="quiet-button" disabled={busy} onClick={() => void inspectEvidence()}>Inspect evidence in Library</button>{evidence.map((item, i) => <a className="quiet-button" key={i} href={sourceLink(item.document_id, item.source_id, { start: item.start_char, end: item.end_char })}>{item.document} · inspect quote →</a>)}</div>
        <label htmlFor="reviewer-name">Reviewer name<input id="reviewer-name" value={reviewer} maxLength={80} disabled={busy} onChange={(event) => setReviewer(event.target.value)} /></label>
        <p className="oracle-session-note">Apply grades consistently across questions: 1 relevant, 2 strongly relevant, 3 essential. Include equivalent relevant passages in both languages where present. Grades and exact quote matches do not prove correctness.</p>
        <label className="evaluation-check"><input id="review-attestation" type="checkbox" checked={attest} disabled={busy} onChange={(event) => setAttest(event.target.checked)} />I personally checked the reference answer, answerability, and all expected supporting evidence against the current library.</label>
        <button className="gold-button" disabled={busy || (attest && reviewer.trim().length < 2)} onClick={() => void saveReview()}>{busy ? 'Working…' : attest ? 'Record personal review' : 'Save unreviewed draft'}</button>
        <p className="oracle-session-note">Approval is a recorded personal attestation, not proof of identity. Library changes invalidate it. Saving without the checkbox leaves or returns the example to draft status. Review all relevant evidence; incomplete labels bias metrics.</p>
      </div>}
    </details>
    <div className="evaluation-run-controls"><h4>Run a development experiment</h4><div className="evaluation-methods">{['bm25', 'dense', 'hybrid'].map((method) => <label className="evaluation-check" key={method}><input type="checkbox" checked={methods.includes(method)} disabled={busy || Boolean(active)} onChange={(event) => setMethods((previous) => event.target.checked ? [...previous, method] : previous.filter((value) => value !== method))} />{method === 'bm25' ? 'BM25 · encoder chunks' : method === 'dense' ? 'Dense · E5 / FAISS' : 'Hybrid · RRF'}</label>)}</div>
      <label className="evaluation-check"><input type="checkbox" checked={reviewedOnly} disabled={busy || Boolean(active)} onChange={(event) => setReviewedOnly(event.target.checked)} />Reviewed examples only</label>
      <p>Unchecked: include unreviewed development cases as diagnostics; their quality metrics remain blank. All methods share the same encoder corpus. Dense/hybrid runs start local workers sequentially and require free RAM. Reranking is not configured.</p>
      <button className="gold-button" disabled={busy || Boolean(active) || methods.length === 0 || (reviewedOnly && reviewedCount === 0)} onClick={() => void run()}>Run retrieval evaluation</button>
      {active && <p role="status">Running {active.completed} / {active.total} retrieval requests…</p>}
    </div>
    <div className="evaluation-reports"><h4>Actual experiment reports</h4>{runs.length === 0 && <p>No runs have been recorded. No performance numbers are available.</p>}
      <div className="evaluation-run-list">{runs.map((item) => <button className="quiet-button" key={item.id} disabled={item.status !== 'complete'} onClick={() => { setError(''); setSelectedRun(item.id) }}>{item.id.slice(0, 8)} · {item.status} · {item.completed}/{item.total}{item.error ? ` · ${item.error}` : ''}</button>)}</div>
      {report && <div className="evaluation-report"><p className="evaluation-notice">Run {report.run_id} · dataset {report.dataset_id} · {report.mode} · development split · quality metrics use only reviewed, answerable cases. A diagnostic is not a held-out quality result.</p>
        <div className="evaluation-actions"><a className="quiet-button" href={`/api/evaluation/runs/${report.run_id}/export?format=json`}>Export JSON</a><a className="quiet-button" href={`/api/evaluation/runs/${report.run_id}/export?format=markdown`}>Export Markdown</a></div>
        <div className="evaluation-table" tabIndex={0} role="region" aria-label="Retrieval metrics table, horizontally scrollable"><table><caption>Measured retrieval results on this report’s shared corpus</caption><thead><tr><th>Method</th><th>Queries / scored</th>{metricLabels.map((label) => <th key={label}>{label}</th>)}<th>Median ms</th><th>p95 ms</th></tr></thead><tbody>{Object.entries(report.summary).map(([method, row]) => <tr key={method}><th>{method}</th><td>{row.query_count} / {row.scored_count}</td>{metricKeys.map((key) => <td key={key}>{metric(row.metrics, key)}</td>)}<td>{row.latency_median_ms?.toFixed(2) ?? '—'}</td><td>{row.latency_p95_ms?.toFixed(2) ?? '—'}</td></tr>)}</tbody></table></div>
        <div className="evaluation-latency" aria-label="Measured median retrieval latency comparison">{Object.entries(report.summary).map(([method, row]) => <div key={method}><span>{method} · median {row.latency_median_ms?.toFixed(2)} ms</span><meter aria-label={`${method} median retrieval latency in milliseconds`} min={0} max={Math.max(1, ...Object.values(report.summary).map((value) => value.latency_median_ms ?? 0))} value={row.latency_median_ms ?? 0} /></div>)}</div>
        <details className="oracle-details"><summary>Language breakdowns and configuration</summary>{Object.entries(report.summary).map(([method, row]) => <div key={method}><h4>{method}</h4>{Object.entries(row.languages ?? {}).map(([language, value]) => <p key={language}>{language}: {value.query_count} queries · {value.scored_count} scored · Recall@5 {value.metrics?.recall_at_5.toFixed(4) ?? 'not scored'} · median {value.latency_median_ms?.toFixed(2) ?? '—'} ms</p>)}</div>)}<p>Dataset fingerprint: <code>{report.dataset_fingerprint}</code></p><p>Chunk corpus: <code>{report.encoder_snapshot.corpus_hash}</code></p><pre>{JSON.stringify(report.configurations, null, 2)}</pre></details>
        <details className="oracle-details"><summary>Limitations and metric definitions</summary><ul>{report.limitations.map((item) => <li key={item}>{item}</li>)}</ul><p>Recall@5: retrieved labelled positives / all labelled positives. Precision@5 always divides by 5. MRR@10 uses the first positive rank. nDCG@5 uses exponential graded gain and log2 discount. Cases with no positive labels are unscored.</p></details>
        <h4>Per-question traces and failure inspection</h4><label className="trace-filter" htmlFor="trace-filter">Find a trace<input id="trace-filter" type="search" dir="auto" value={traceQuery} onChange={(event) => { setTraceQuery(event.target.value); setTraceLimit(20) }} placeholder="Question, ID, or retrieval method" /></label><p role="status">Showing {Math.min(traceLimit, matchingTraces.length)} of {matchingTraces.length} matching traces. Exports include the full report.</p>{matchingTraces.slice(0, traceLimit).map((result) => <details className="evaluation-trace" key={`${result.example_id}:${result.method}`}><summary><span>{result.example_id} · {result.method} · {result.review_status} · {result.latency_ms.toFixed(2)} ms</span><bdi>{result.question}</bdi></summary><p dir="auto">Reference candidate: {result.reference_answer}</p>{result.hits.length === 0 && <p>No passages matched.</p>}<ol>{result.hits.map((hit) => <li key={hit.chunk_id}><strong>{hit.filename}</strong><p dir="auto">{hit.excerpt}</p><a href={sourceLink(hit.document_id, hit.source_id, { start: hit.start_char, end: hit.end_char })}>Inspect retrieved source →</a></li>)}</ol></details>)}{matchingTraces.length > traceLimit && <button className="quiet-button" onClick={() => setTraceLimit((count) => count + 20)}>Show 20 more traces</button>}
      </div>}
    </div>
  </section>
}
