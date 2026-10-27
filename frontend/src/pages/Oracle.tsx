import { useEffect, useRef, useState } from 'react'
import { askOracle, getOracleStatus, listConversations, getConversation, deleteConversation, createTicket,
  type OracleAnswer, type OracleStatus, type ConversationMetadata } from '../services/api'
import { sourceLink } from '../services/sourceLinks'
import ModuleIcon from '../components/ModuleIcon'

export default function Oracle() {
  const [status, setStatus] = useState<OracleStatus | null>(null)
  const [refresh, setRefresh] = useState(0)
  const [question, setQuestion] = useState('')
  const [history, setHistory] = useState<OracleAnswer[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const readConversation = () => window.location.hash.startsWith('#oracle?')
    ? new URLSearchParams(window.location.hash.split('?')[1]).get('conversation') : null
  const [activeId, setActiveId] = useState<string | null>(readConversation)
  const activeRef = useRef(activeId)
  const [revision, setRevision] = useState<number | null>(null)
  const [conversations, setConversations] = useState<ConversationMetadata[]>([])
  const [loading, setLoading] = useState(Boolean(activeId))
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [handoffBusy, setHandoffBusy] = useState<string | null>(null)
  const [handoffError, setHandoffError] = useState('')
  const composer = useRef<HTMLTextAreaElement>(null)
  const transcript = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const panel = transcript.current
    if (panel) panel.scrollTop = panel.scrollHeight
  }, [history.length, busy, activeId])

  function selectConversation(id: string | null) {
    activeRef.current = id
    setActiveId(id)
    setHistory([])
    setRevision(null)
    setConfirmDelete(false)
    setError('')
    window.history.replaceState(null, '', id ? `#oracle?conversation=${encodeURIComponent(id)}` : '#oracle')
  }

  useEffect(() => {
    const navigate = () => {
      if (window.location.hash.split('?')[0] === '#oracle') setRefresh((value) => value + 1)
      const requested = readConversation()
      if (requested && requested !== activeRef.current) {
        activeRef.current = requested
        setActiveId(requested)
        setHistory([])
        setRevision(null)
      } else if (window.location.hash === '#oracle' && activeRef.current) {
        window.history.replaceState(null, '', `#oracle?conversation=${encodeURIComponent(activeRef.current)}`)
      }
    }
    window.addEventListener('hashchange', navigate)
    return () => window.removeEventListener('hashchange', navigate)
  }, [])

  useEffect(() => {
    if (!activeId) { setLoading(false); return }
    const controller = new AbortController()
    setLoading(true)
    getConversation(activeId, controller.signal).then((detail) => {
      if (!controller.signal.aborted) { setHistory(detail.turns); setRevision(detail.revision) }
    }).catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Conversation unavailable.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [activeId, refresh])

  useEffect(() => {
    const controller = new AbortController()
    getOracleStatus(controller.signal).then(setStatus).catch((reason) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Readiness check failed.')
    })
    listConversations(controller.signal).then(setConversations).catch((reason) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Saved conversations unavailable.')
    })
    return () => controller.abort()
  }, [refresh])

  async function ask() {
    const selectedId = activeRef.current
    setBusy(true)
    setError('')
    try {
      const answer = await askOracle(question.trim(), selectedId ?? undefined, revision ?? undefined)
      if (activeRef.current === selectedId) {
        activeRef.current = answer.conversation_id
        setActiveId(answer.conversation_id)
        setRevision(answer.conversation_revision)
        setHistory((previous) => [...previous, answer])
        if (!window.location.hash || window.location.hash.split('?')[0] === '#oracle') {
          window.history.replaceState(null, '', `#oracle?conversation=${answer.conversation_id}`)
        }
        setQuestion('')
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Answer generation failed.') }
    finally { setBusy(false); setRefresh((value) => value + 1) }
  }

  async function removeSaved() {
    if (!activeId) return
    setBusy(true)
    try { await deleteConversation(activeId); selectConversation(null); setRefresh((value) => value + 1) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Deletion failed.') }
    finally { setBusy(false) }
  }

  async function handoff(answer: OracleAnswer) {
    setHandoffBusy(answer.turn_id)
    setHandoffError('')
    try {
      const result = await createTicket(answer.conversation_id,answer.turn_id)
      setHistory((previous) => previous.map((turn) => turn.turn_id === answer.turn_id ? { ...turn, ticket_id: result.ticket.id } : turn))
    } catch (reason) { setHandoffError(reason instanceof Error ? reason.message : 'Ticket creation failed.') }
    finally { setHandoffBusy(null) }
  }

  const ready = (status?.runtime.state === 'ready' || status?.runtime.state === 'configured') && status.retrieval === 'ready' && !status.busy
  const cloud = status?.runtime.provider === 'gemini'
  const canAsk = ready && !busy && !loading && (!activeId || revision !== null) && history.length < 30 && Boolean(question.trim())
  const readiness = !status ? 'Checking configuration' : status.busy ? 'Finishing a previous request' : status.runtime.state === 'key_missing' ? 'Generation key needed' : !['ready', 'configured'].includes(status.runtime.state) ? 'Generation unavailable' : status.retrieval !== 'ready' ? 'Knowledge index needed' : 'Ready to ask'
  const starters = [
    { label: 'Returns & refunds', question: 'What is the return policy?', lang: 'en' },
    { label: 'طلب متأخر', question: 'لو الأوردر اتأخر أعمل إيه؟', lang: 'ar' },
  ]

  return <section className="oracle oracle-workspace" aria-labelledby="oracle-heading">
    <header className="oracle-toolbar">
      <div className="oracle-title"><ModuleIcon name="oracle" /><div><p className="eyebrow text-gold">CONSULT THE ORACLE</p><h2 id="oracle-heading">Your conversation</h2></div></div>
      <button className="quiet-button" disabled={busy} onClick={() => { selectConversation(null); setQuestion(''); composer.current?.focus() }}><span aria-hidden="true">＋</span> New conversation</button>
    </header>
    <div className="oracle-layout">
      <div className="oracle-chat">
        <div className="conversation-controls">
          <label htmlFor="saved-conversation">Conversation history<select id="saved-conversation" value={activeId ?? ''} disabled={busy} onChange={(event) => selectConversation(event.target.value || null)}><option value="">New conversation</option>{conversations.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.turn_count} turns</option>)}</select></label>
          {activeId && <button className="quiet-button conversation-delete-trigger" disabled={busy || Boolean(handoffBusy)} onClick={() => setConfirmDelete(true)} aria-label="Delete conversation">Delete</button>}
        </div>
        {confirmDelete && <div className="conversation-delete" role="alert"><p>Delete this saved conversation and its answer/quote snapshots? This cannot be undone. Existing support tickets retain their own snapshots.</p><button className="quiet-button" disabled={busy || Boolean(handoffBusy)} onClick={() => void removeSaved()}>Confirm delete conversation</button><button className="quiet-button" disabled={busy} onClick={() => setConfirmDelete(false)}>Cancel</button></div>}
        <div className="oracle-history" ref={transcript} role="log" aria-label="Conversation messages" aria-live={loading ? 'off' : 'polite'} aria-busy={busy || loading} tabIndex={0}>
          {loading ? <p className="oracle-loading" role="status">Opening your saved conversation…</p> : history.length === 0 && !busy ? <div className="oracle-welcome">
            <div className="oracle-sigil"><ModuleIcon name="oracle" /></div><p className="eyebrow text-gold">LET KNOWLEDGE SPEAK</p><h3>What would you like to know?</h3><p>Ask about your company’s documents.<br />Follow the evidence behind every answer.</p>
            <div className="oracle-starters">{starters.map((starter) => <button key={starter.lang} type="button" disabled={busy} onClick={() => { setQuestion(starter.question); composer.current?.focus() }}><span lang={starter.lang} dir="auto">{starter.label}</span><span aria-hidden="true">↗</span></button>)}</div>
          </div> : null}
          {history.map((answer) => {
            const citedIds = new Set(answer.claims.flatMap((claim) => claim.evidence.map((item) => item.source_id)))
            const citedSources = answer.sources.filter((source) => citedIds.has(source.source_id))
            return <article className="oracle-turn" key={answer.turn_id}>
              <div className="oracle-question"><span className="eyebrow">YOU</span><p dir="auto">{answer.question}</p></div>
              <div className="oracle-answer">
                <div className="answer-identity"><ModuleIcon name="oracle" /><span>The Oracle</span><span className={`answer-state ${answer.status}`}>{answer.status === 'answered' ? 'Source-linked draft' : answer.status === 'needs_clarification' ? 'More detail needed' : 'Human review needed'}</span></div>
                {answer.sources.some((source) => source.citation_state !== 'current') && <p className="stale-citation" role="status">Some saved sources changed or were deleted. These are historical quotes; ask again using the current knowledge base.</p>}
                {answer.status === 'needs_clarification' ? <p dir="auto">{/[\u0600-\u06ff]/.test(answer.question) ? 'يرجى ذكر المنتج والسياسة المقصودين في سؤال كامل. لا أستنتج المقصود من الردود السابقة.' : 'Please name the product and policy in a complete question. I do not infer missing details from previous answers.'}</p> : answer.status === 'needs_human' ? <p dir="auto">{/[\u0600-\u06ff]/.test(answer.question) ? 'لا أستطيع تقديم إجابة موثقة كافية من المصادر المتاحة. يمكنك حفظ السؤال في تذكرة محلية لمراجعة بشرية. لا يتم إرسال رسائل.' : 'The available evidence is not enough for a sourced answer. You can save this question in a local ticket for human review. No message is sent.'}</p> : answer.claims.map((claim, claimIndex) => <div className="oracle-claim" key={claimIndex}><p dir="auto">{claim.text}</p><div className="oracle-citations">{Array.from(new Set(claim.evidence.map((evidence) => evidence.source_id))).map((id) => {
                  const source = answer.sources.find((item) => item.source_id === id)
                  return source && (source.citation_state === 'current' ? <a key={id} href={sourceLink(source.document_id, source.id, { start: source.start_char, end: source.end_char })} aria-label={`View evidence ${id} in ${source.filename}`}>Evidence {id} ↗</a> : <span className="stale-citation" key={id}>{id} · {source.citation_state}</span>)
                })}</div></div>)}
                {citedSources.length > 0 && <div className="answer-sources"><p className="eyebrow">SOURCES TO CHECK</p><div className="source-card-grid">{citedSources.map((source) => {
                  const content = <><span className="source-card-ref">{source.source_id}</span><span><strong>{source.filename}</strong><small>{source.section || 'Document passage'}</small></span><span aria-hidden="true">↗</span></>
                  return source.citation_state === 'current' ? <a className="answer-source-card" key={source.source_id} href={sourceLink(source.document_id, source.id, { start: source.start_char, end: source.end_char })} aria-label={`View source ${source.source_id}: ${source.filename}`}>{content}</a> : <div className="answer-source-card source-unavailable" key={source.source_id}>{content}<small>Historical source · {source.citation_state}</small></div>
                })}</div></div>}
                {answer.claims.length > 0 && <details className="oracle-quotes"><summary>Supporting quotes</summary>{answer.claims.flatMap((claim, claimIndex) => claim.evidence.map((evidence, evidenceIndex) => <blockquote key={`${claimIndex}:${evidenceIndex}`}><span>{evidence.source_id}</span><p dir="auto">{evidence.quote}</p></blockquote>))}<p>These quotes matched the evidence when generated. Check current sources and whether they support each claim.</p></details>}
                <div className="answer-footer"><details className="oracle-details"><summary>Answer details · {(answer.latency_ms / 1000).toFixed(2)} s</summary><p>{answer.model} · {answer.prompt_version}</p>{answer.model_digest && <p>Model digest: <code>{answer.model_digest}</code></p>}{answer.model_version && <p>Hosted model version: <code>{answer.model_version}</code></p>}{answer.corpus_hash && <p>Chunk corpus: <code>{answer.corpus_hash}</code></p>}{answer.reason && <p>Review reason: {answer.reason}</p>}</details>
                  <div className="oracle-handoff">{answer.ticket_id ? <a className="quiet-button" href={`#dispatch?ticket=${answer.ticket_id}`}><ModuleIcon name="dispatch" /> Open local ticket</a> : <button className={`quiet-button ${answer.status === 'needs_human' ? 'handoff-emphasis' : ''}`} disabled={busy || Boolean(handoffBusy)} onClick={() => void handoff(answer)}><ModuleIcon name="dispatch" />{handoffBusy === answer.turn_id ? 'Creating ticket…' : 'Request human review'}</button>}</div>
                </div>
                <p className="handoff-disclosure">Human review creates a ticket on this computer. No email or customer message is sent.</p>
              </div>
            </article>
          })}
          {busy && <div className="oracle-pending"><p dir="auto">{question.trim()}</p><div role="status"><ModuleIcon name="oracle" /><span>Reading your sources and preparing an answer…</span><span className="thinking-dots" aria-hidden="true"><i /><i /><i /></span></div></div>}
        </div>
        {error && <p className="library-error" role="alert">{error}</p>}
        {handoffError && <p className="library-error" role="alert">{handoffError}</p>}
        <form className="oracle-composer" onSubmit={(event) => { event.preventDefault(); if (canAsk) void ask() }}>
          <label htmlFor="oracle-question">Your question <span lang="ar">/ سؤالك</span></label>
          <textarea ref={composer} id="oracle-question" dir="auto" maxLength={500} required value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !event.nativeEvent.isComposing) { event.preventDefault(); if (canAsk) event.currentTarget.form?.requestSubmit() } }} placeholder="Ask a complete question in English or Arabic…" disabled={busy || loading} />
          <div className="oracle-actions"><span>{question.length} / 500 <span className="composer-shortcut">· Ctrl / ⌘ + Enter to send</span></span><button className="gold-button" type="submit" disabled={!canAsk}>{busy ? 'Preparing answer…' : 'Ask The Oracle'}<span aria-hidden="true">↑</span></button></div>
          <p className="composer-disclosure">{cloud ? 'Gemini receives your question and selected document passages.' : status ? 'Questions and document passages are processed locally.' : 'Checking the generation provider…'} Answers are drafts; check the evidence.</p>
          {history.length >= 30 && <p className="library-error" role="status">This conversation has reached 30 turns. Start a new conversation to continue.</p>}
        </form>
      </div>
      <aside className="oracle-context" aria-label="Oracle guidance and configuration">
        <div className={`oracle-availability ${ready ? 'available' : ''}`} role="status"><span className="availability-light" /><div><strong>{readiness}</strong><p>{ready ? cloud ? 'Connection and quota are checked when you send.' : 'Local model and knowledge index available.' : 'Review the setup details below.'}</p></div></div>
        <div className="oracle-guide"><ModuleIcon name="library" /><h3>Grounded in your library</h3><p>Ask a complete question each time. The Oracle uses your documents and cannot check live orders or perform actions.</p><a href="#library">Explore your knowledge <span aria-hidden="true">↗</span></a></div>
        <details className="oracle-details oracle-data"><summary>Privacy & answer limitations</summary><p>{cloud ? 'Retrieval and saved conversations stay on this computer. Gemini receives your question and selected passages. Free-tier content may be used by Google to improve its products; use fictional demo data.' : 'In local mode, retrieval and generation run on this computer.'}</p><p>Quality evaluation remains pending. Source IDs and exact quotes are checked; this does not establish correctness.</p><p>Previous turns are not sent to the model. Saved answers and quotes remain until you delete the conversation, even if a Library document is deleted. Existing support tickets keep their own copies.</p><p>Up to 100 saved conversations, 30 turns each.</p></details>
        <details className="oracle-details oracle-setup" open={!ready && Boolean(status)}><summary>Connection & model settings</summary>{status && <><p>{status.runtime.model} · {cloud ? 'Google Gemini API' : `local runtime ${status.runtime.runtime_version ?? 'offline'}`}</p><p>{status.runtime.state === 'key_missing' ? 'Set GEMINI_API_KEY in the backend environment or ignored .env, restart the API, then refresh.' : !['ready', 'configured'].includes(status.runtime.state) ? 'Check the generation service and configured model, then refresh.' : status.retrieval !== 'ready' ? 'Prepare a current encoder index in Athena’s Library.' : 'Generation is configured. Readiness does not guarantee connectivity or available quota.'}</p><p>{cloud ? `${status.prompt_budget_bytes}-byte evidence budget` : `${status.context_tokens}-token context`} · {status.output_tokens}-token output cap</p><p>{(status.available_ram_mib / 1024).toFixed(2)} GiB available RAM at last check. {cloud ? 'Retrieval embeddings run locally; Gemini generation requires internet.' : 'Encoder and generator run sequentially and unload after use.'}</p></>}<button className="quiet-button" onClick={() => { setError(''); setRefresh((value) => value + 1) }} disabled={busy}>Refresh readiness</button></details>
        <div className="oracle-session-note"><span aria-hidden="true">◇</span><p>{history.length > 0 ? `${history.length} / 30 turns · saved on this computer` : 'Your conversation is saved on this computer after you ask.'}</p></div>
      </aside>
    </div>
  </section>
}
