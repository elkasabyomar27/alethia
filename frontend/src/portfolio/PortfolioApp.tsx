import { useEffect, useRef, useState } from 'react'
import MythicArtwork, { moduleArtwork } from '../components/MythicArtwork'
import ModuleIcon, { type ModuleName } from '../components/ModuleIcon'
import { portfolioData, evidenceLink, type Metrics, type SavedExample } from './data'
import './portfolio.css'

const modules: { id: ModuleName; title: string; label: string; description: string }[] = [
  { id: 'oracle', title: 'The Oracle', label: 'Saved answer walkthrough', description: 'Explore how business documents become English and Arabic answer drafts, with evidence you can inspect.' },
  { id: 'library', title: 'Athena’s Library', label: 'Fictional knowledge collection', description: 'Follow each citation back to the original fictional policy. All six Helios Home documents are available here.' },
  { id: 'tribunal', title: 'Themis’ Tribunal', label: 'Actual development experiment', description: 'Inspect measured retrieval results, sample sizes, and the limits of a provisional pilot.' },
  { id: 'dispatch', title: 'Hermes’ Dispatch', label: 'Illustrative handoff walkthrough', description: 'See how an unsupported question can become an explicit local review ticket.' },
]
function readRoute(): ModuleName { return modules.find(m => `#${m.id}` === location.hash.split('?')[0])?.id ?? 'oracle' }

export default function PortfolioApp() {
  const [active, setActive] = useState<ModuleName>(readRoute)
  const [source, setSource] = useState(() => new URLSearchParams(location.hash.split('?')[1]).get('source'))
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    const navigate = () => {
      setActive(readRoute())
      setSource(new URLSearchParams(location.hash.split('?')[1]).get('source'))
    }
    window.addEventListener('hashchange', navigate)
    return () => window.removeEventListener('hashchange', navigate)
  }, [])
  useEffect(() => { heading.current?.focus({ preventScroll: true }); window.scrollTo({ top: 0 }) }, [active])
  const current = modules.find(m => m.id === active)!
  return <div className="app-shell sanctuary-shell portfolio-shell" data-module={active}>
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className="sidebar"><a className="brand" href="#oracle" aria-label="ALETHIA home"><span className="brand-mark">Α</span><span>ALETHIA<small>Α Λ Η Θ Ε Ι Α</small></span></a><div className="sidebar-rule" /><p className="eyebrow nav-caption">EXPLORE THE PROJECT</p>
      <nav aria-label="Main navigation">{modules.map(m => <a className={`nav-link ${active === m.id ? 'active' : ''}`} href={`#${m.id}`} key={m.id} aria-current={active === m.id ? 'page' : undefined}><ModuleIcon name={m.id} className="nav-icon" /><span>{m.title}<small>{m.label}</small></span></a>)}</nav>
      <div className="sidebar-bottom"><p>A personal engineering project.<br />Where Knowledge Becomes Answers.</p><span className="eyebrow">FICTIONAL DATA · TRACEABLE EVIDENCE</span></div>
    </aside>
    <div className="workspace"><header className="portfolio-banner"><strong>Guided demo — saved examples</strong><span>Read-only · no live AI requests</span></header>
      <main id="main-content" tabIndex={-1}><section className="module-header" aria-labelledby="page-heading"><MythicArtwork module={active} /><div className="module-copy"><p className="eyebrow text-gold">{current.label}</p><h1 id="page-heading" ref={heading} tabIndex={-1}>{current.title}</h1><p>{current.description}</p></div></section>
        <div className="content-area">
          {active === 'oracle' ? <OracleDemo /> : active === 'library' ? <LibraryDemo source={source} /> : active === 'tribunal' ? <PilotDemo /> : <DispatchDemo />}
          <details className="portfolio-notes"><summary>Architecture, setup, and project limitations</summary><p>ALETHIA helps people find support policy evidence and draft answers. The full local app supports document ingestion, hybrid retrieval, saved conversations, and human review tickets.</p>
            <ol className="architecture-flow"><li>PDF / DOCX / TXT / Markdown</li><li>Bounded extraction and source references</li><li>BM25 + multilingual E5 INT8 / FAISS → RRF</li><li>Gemini or optional local generation</li><li>Quote checks → draft or local handoff</li></ol>
            <p>The full app runs on Windows with Python 3.11, Node 24, SQLite, FastAPI, and React. Gemini requires internet and provider configuration; optional local inference remains available. This showcase is a static build containing only selected fictional material. It cannot upload, generate, modify data, or send tickets.</p>
            <p>Quote validation does not guarantee correct reasoning. The pilot measures retrieval only. Reranking, final held-out evaluation, and generation/handoff quality evaluation remain unfinished.</p>
            <p>Local startup, after dependencies are installed:</p><pre>{'.\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000\n# Separate terminal, from frontend/:\nnpm.cmd run dev'}</pre>
            <a href="/project/README.md">Setup documentation</a> · <a href="/project/portfolio-case-study.md">Case study</a> · <a href="/project/demo-walkthrough.md">Walkthrough</a>
            <details><summary>Full local application screenshots</summary><p>Historical captures of the full local app using fictional data; these are not screenshots of live inference or this guided build.</p><img className="portfolio-screenshot" src="/project/oracle-desktop.png" alt="Full local Oracle conversation entry screen with Apollo artwork" loading="lazy" width="1440" height="1050" /><img className="portfolio-screenshot" src="/project/library-desktop.png" alt="Full local Library showing the filtered fictional returns document and source inspector" loading="lazy" width="1440" height="1050" /></details>
          </details>
          <footer className="workspace-footer"><span>ALETHIA · Personal project showcase</span><details className="art-credits"><summary>Artwork credits</summary><p>Public-domain <a href={`https://commons.wikimedia.org/wiki/File:${moduleArtwork[active].source}`} target="_blank" rel="noreferrer">{moduleArtwork[active].name} engraving</a>, displayed with CSS tinting, cropping, and motion.</p></details></footer>
        </div>
      </main>
    </div>
  </div>
}

function OracleDemo() {
  const examples = portfolioData.examples()
  const [selected, setSelected] = useState(examples[0].id)
  const [playing, setPlaying] = useState(false)
  const [revealed, setRevealed] = useState(0)
  const example = examples.find(e => e.id === selected)!
  useEffect(() => {
    if (!playing || revealed >= example.claims.length) return
    const timer = window.setTimeout(() => setRevealed(value => value + 1), 850)
    return () => window.clearTimeout(timer)
  }, [playing, revealed, example])
  const select = (id: string) => { setSelected(id); setPlaying(false); setRevealed(0) }
  return <>
    <section className="portfolio-intro"><p className="eyebrow text-gold">WHERE KNOWLEDGE BECOMES ANSWERS</p><h2>Support answers you can trace.</h2><p>Policies are scattered. Fluent answers can miss exceptions. ALETHIA connects a question to its source passages, then makes uncertainty and review visible.</p><div className="portfolio-tags"><span>English & Arabic</span><span>Source-linked drafts</span><span>Hybrid retrieval</span><span>Explicit handoff</span></div></section>
    <section className="portfolio-panel" aria-labelledby="saved-demo"><h2 id="saved-demo">Explore a saved conversation</h2><p>Choose an example, then replay its saved answer. Playback reveals existing text; it does not call an AI model.</p>
      <div className="example-picker" role="group" aria-label="Saved examples">{examples.map(e => <button key={e.id} className={`quiet-button ${selected === e.id ? 'chosen' : ''}`} aria-pressed={selected === e.id} onClick={() => select(e.id)} dir="auto">{e.label}</button>)}</div>
      <div className="demo-question" dir="auto"><span>Saved question</span><p>{example.question}</p></div>
      <div className="playback-controls"><button className="gold-button" onClick={() => { setRevealed(window.matchMedia('(prefers-reduced-motion: reduce)').matches ? example.claims.length : 0); setPlaying(true) }}>Replay saved answer</button><button className="quiet-button" onClick={() => { setRevealed(example.claims.length); setPlaying(true) }}>Show complete answer</button></div>
      <div className="demo-answer" aria-live="polite" aria-atomic="false">{!playing ? <p>Ready to explore this saved example.</p> : example.status === 'needs_human' ? <><h3>Human review needed</h3><p>The fictional documents do not provide live stock counts. No answer was accepted for this saved turn.</p><a className="quiet-button" href="#dispatch">Explore the illustrative handoff →</a></> : <>{example.claims.slice(0, revealed).map((claim, i) => <article key={i}><p dir="auto">{claim.text}</p><div className="demo-citations">{claim.evidence.map((citation, j) => <a key={j} href={evidenceLink(citation.sourceId)}>Inspect supporting source ↗</a>)}</div><details><summary>Saved supporting quotes</summary>{claim.evidence.map((citation,j) => <blockquote dir="auto" key={j}>{citation.quote}</blockquote>)}</details></article>)}{revealed < example.claims.length && <p>Replaying saved text…</p>}</>}</div>
      <p className="demo-disclosure">Saved {new Date(example.savedAt).toLocaleDateString()} · model: {example.model}. Example output is a draft, not a general accuracy claim. Each full-app question is handled independently.</p>
    </section>
    <section className="portfolio-panel"><h2>See the complete workflow</h2><p>Inspect fictional sources in Athena’s Library, see real retrieval measurements in Themis’ Tribunal, and explore the local review workflow in Hermes’ Dispatch.</p><div className="portfolio-links"><a href="#library">Browse documents →</a><a href="#tribunal">Inspect actual pilot →</a><a href="#dispatch">Explore handoff →</a></div></section>
  </>
}

function LibraryDemo({ source }: { source: string | null }) {
  const documents = portfolioData.documents()
  const selection = documents.find(d => d.sections.some(s => s.id === source))
  const [selected, setSelected] = useState(selection?.id ?? documents[0].id)
  const [query, setQuery] = useState('')
  useEffect(() => { if (selection) setSelected(selection.id) }, [selection])
  useEffect(() => { if (source) document.getElementById(source)?.focus() }, [source, selected])
  const current = documents.find(d => d.id === selected)!
  const filtered = documents.filter(d => d.filename.toLowerCase().includes(query.trim().toLowerCase()))
  return <section className="portfolio-panel"><h2>Helios Home knowledge pack</h2><p>Six fictional e-commerce policies. Upload and editing are available in the full local app. This public collection is read-only.</p><label className="portfolio-field">Find a document<input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Filter by filename" /></label>
    {source && !portfolioData.source(source) && <p role="alert" className="library-error">This saved source link is unavailable. Choose a document below.</p>}
    <div className="demo-library-grid"><nav aria-label="Fictional documents">{filtered.map(d => <button key={d.id} className={`quiet-button ${selected === d.id ? 'chosen' : ''}`} aria-pressed={selected === d.id} onClick={() => { setSelected(d.id); location.hash = '#library' }}>{d.filename}</button>)}{filtered.length === 0 && <p role="status">No matching documents.</p>}</nav><div><h3>{current.filename}</h3>{current.sections.map(s => <article key={s.id} id={s.id} tabIndex={-1} className={`demo-source ${source === s.id ? 'selected-source' : ''}`}><h4>{s.title}</h4><pre dir="auto">{s.text}</pre><a href={evidenceLink(s.id)}>Link to this source</a></article>)}</div></div>
  </section>
}

function PilotDemo() {
  const pilot = portfolioData.pilot()
  const keys: (keyof Metrics)[] = ['recall_at_5', 'precision_at_5', 'mrr_at_10', 'ndcg_at_5']
  return <section className="portfolio-panel"><p className="eyebrow text-gold">PROVISIONAL DEVELOPMENT PILOT</p><h2>Measured retrieval, with its limits.</h2><p>{pilot.samples} reviewed questions · {pilot.answerable} answerable questions scored per method · {pilot.groups} intent groups. English {pilot.languages.en}, Modern Standard Arabic {pilot.languages.ar_msa}, Egyptian Arabic {pilot.languages.ar_egy}.</p><p className="evaluation-notice">A small, selected development subset; this is not a held-out test or a generation-quality evaluation. {pilot.samples - pilot.answerable} unanswerable cases contribute latency only.</p>
    <div className="evaluation-table" tabIndex={0} role="region" aria-label="Pilot metrics, horizontally scrollable"><table><caption>Actual stored run · {new Date(pilot.completedAt).toLocaleDateString()}</caption><thead><tr><th>Method</th><th>Scored / queries</th><th>Recall@5</th><th>Precision@5</th><th>MRR@10</th><th>nDCG@5</th><th>Median ms</th><th>p95 ms</th></tr></thead><tbody>{Object.entries(pilot.summary).map(([name,r]) => <tr key={name}><th>{name}</th><td>{r.scored_count} / {r.query_count}</td>{keys.map(k => <td key={k}>{r.metrics?.[k].toFixed(4) ?? 'Not scored'}</td>)}<td>{r.latency_median_ms?.toFixed(2)}</td><td>{r.latency_p95_ms?.toFixed(2)}</td></tr>)}</tbody></table></div>
    <p>All methods use the same encoder chunks. Dense and hybrid latency includes cold embedding-worker startup on the constrained laptop. Scores depend on the current human-supplied evidence labels.</p>
    <details><summary>Language-specific results</summary>{Object.entries(pilot.summary).map(([method,r]) => <div key={method}><h3>{method}</h3>{Object.entries(r.languages).map(([lang,v]) => <p key={lang}>{lang}: {v.query_count} queries / {v.scored_count} scored · Recall@5 {v.metrics?.recall_at_5.toFixed(4) ?? 'Not scored'} · median {v.latency_median_ms?.toFixed(2) ?? '—'} ms</p>)}</div>)}</details>
    <details><summary>Failure examples and limitations</summary>{pilot.failures.length ? pilot.failures.map((f,i) => <p key={i}>{f.method} · {f.question} · Recall@5 {f.recall.toFixed(4)}</p>) : <p>The curated answer examples are not a representative failure sample. See the pilot report for aggregate failure analysis.</p>}<ul>{pilot.limitations.map(l => <li key={l}>{l}</li>)}</ul></details>
    <details><summary>Reproducibility identifiers</summary><p>Run: {pilot.runId}</p><p>Corpus: <code>{pilot.corpusHash}</code></p><p>Dataset snapshot: <code>{pilot.datasetFingerprint}</code></p><p>The local full report retains the review snapshot and per-question traces; they are excluded from this public build.</p></details><p><a href="/project/pilot-summary.md">Read the pilot summary</a></p>
  </section>
}

function DispatchDemo() {
  const example: SavedExample = portfolioData.examples().find(e => e.id === 'unsupported')!
  const [step, setStep] = useState(0)
  return <section className="portfolio-panel"><p className="eyebrow text-gold">ILLUSTRATIVE WORKFLOW · NO TICKET IS CREATED</p><h2>Make uncertainty actionable.</h2><p>Saved unsupported question: <strong>{example.question}</strong></p><ol className="handoff-steps"><li>The documents cannot establish live inventory.</li><li>A person explicitly requests human review.</li><li>The full local app stores a ticket with the question, reason, evidence snapshot, and activity.</li><li>A support reviewer records a note and changes its status.</li></ol><button className="gold-button" onClick={() => setStep(s => (s + 1) % 3)}>{step === 0 ? 'Show illustrative ticket' : step === 1 ? 'Show illustrative resolution' : 'Reset walkthrough'}</button>{step > 0 && <div className="illustrative-ticket" aria-live="polite"><span className="ticket-status">Illustrative · {step === 1 ? 'Open' : 'Resolved'}</span><h3>Live stock request needs review</h3><p>Question: {example.question}</p><p>Reason: evidence was insufficient.</p>{step === 2 && <p>Example resolution note: a reviewer checks the business inventory system and records the outcome. ALETHIA itself has no live-stock access.</p>}</div>}<p className="demo-disclosure">This is a UI illustration, not a saved resolution or a claim that inventory was checked. No customer message or email is sent.</p></section>
}
