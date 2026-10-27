import { useEffect, useRef, useState } from 'react'
import { deleteTicket, getTicket, listTickets, updateTicket, type TicketDetail, type TicketStatus, type TicketSummary } from '../services/api'
import { sourceLink } from '../services/sourceLinks'

const statusLabel = { open: 'Open', in_progress: 'In progress', resolved: 'Resolved' }
const reasons: Record<string, string> = {
  insufficient_evidence: 'Evidence was insufficient', no_evidence: 'No usable evidence', invalid_citations: 'Citation validation failed',
  invalid_output: 'Answer format could not be validated', incomplete_answer: 'Requested numeric detail was missing',
  unsafe_request: 'Request matched an instruction-override pattern', unsafe_context: 'Evidence matched an instruction-override pattern',
  requested_review: 'Human review requested', clarification_review: 'Question needs clarification', unsupported_question: 'Unsupported question',
}
const date = (value: string) => new Date(value).toLocaleString(undefined, { timeZone: 'Africa/Cairo' })
const readTicket = () => window.location.hash.split('?')[0] === '#dispatch'
  ? new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('ticket') : null

export default function Dispatch() {
  const [tickets, setTickets] = useState<TicketSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(readTicket)
  const selectedRef = useRef(selectedId)
  const [detail, setDetail] = useState<TicketDetail | null>(null)
  const [filter, setFilter] = useState<TicketStatus | 'all'>('all')
  const [nextStatus, setNextStatus] = useState<TicketStatus>('open')
  const [note, setNote] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const [detailError, setDetailError] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [ticketQuery, setTicketQuery] = useState('')
  const visibleTickets = tickets.filter((ticket) => `${ticket.id} ${ticket.question}`.toLocaleLowerCase().includes(ticketQuery.trim().toLocaleLowerCase()))

  useEffect(() => {
    const navigate = () => { if (window.location.hash.split('?')[0] === '#dispatch') { selectedRef.current = readTicket(); setSelectedId(selectedRef.current) } }
    window.addEventListener('hashchange', navigate)
    return () => window.removeEventListener('hashchange', navigate)
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    listTickets(filter, controller.signal).then((result) => { if (!controller.signal.aborted) setTickets(result) })
      .catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Tickets unavailable.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [filter, refresh])

  useEffect(() => {
    setDetail(null)
    setDetailError('')
    setConfirmDelete(false)
    if (!selectedId) { setDetailLoading(false); return }
    const controller = new AbortController()
    setDetailLoading(true)
    getTicket(selectedId, controller.signal).then((result) => {
      if (!controller.signal.aborted) { setDetail(result); setNextStatus(result.status) }
    }).catch((reason) => { if (!controller.signal.aborted) setDetailError(reason instanceof Error ? reason.message : 'Ticket unavailable.') })
      .finally(() => { if (!controller.signal.aborted) setDetailLoading(false) })
    return () => controller.abort()
  }, [selectedId, refresh])

  async function save() {
    if (!detail) return
    setWorking(true)
    setDetailError('')
    const identity = detail.id
    try {
      const result = await updateTicket(detail.id, detail.revision, nextStatus, note.trim())
      if (selectedRef.current === identity) { setDetail(result); setNote('') }
      setRefresh((value) => value + 1)
    } catch (reason) { if (selectedRef.current === identity) setDetailError(reason instanceof Error ? reason.message : 'Update failed.') }
    finally { setWorking(false) }
  }

  async function remove() {
    if (!detail) return
    setWorking(true)
    const identity = detail.id
    try {
      await deleteTicket(detail.id, detail.revision)
      if (selectedRef.current === identity) {
        selectedRef.current = null
        setSelectedId(null)
        setDetail(null)
        setNote('')
        window.location.hash = '#dispatch'
      }
      setRefresh((value) => value + 1)
    } catch (reason) { if (selectedRef.current === identity) setDetailError(reason instanceof Error ? reason.message : 'Deletion failed.') }
    finally { setWorking(false) }
  }

  return <section className="dispatch" aria-labelledby="dispatch-heading">
    <div className="oracle-heading"><div><p className="eyebrow text-gold">HERMES’ DISPATCH · HUMAN HANDOFF</p><h2 id="dispatch-heading">A question deserves a human.</h2></div><span className="search-method">LOCAL SUPPORT TICKETS</span></div>
    <p className="oracle-guidance">Create a ticket from a saved Oracle answer, review its evidence, and track the work here. Tickets and notes stay on this computer. Creating or resolving a ticket does not send a message to a customer.</p>
    <div className="dispatch-toolbar"><label htmlFor="ticket-filter">Ticket status<select id="ticket-filter" value={filter} disabled={working} onChange={(event) => setFilter(event.target.value as typeof filter)}><option value="all">All statuses</option>{Object.entries(statusLabel).map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label><button className="quiet-button" disabled={working} onClick={() => setRefresh((value) => value + 1)}>Refresh tickets</button><a className="quiet-button" href="#oracle">Go to The Oracle →</a></div>
    {error && <p className="library-error" role="alert">{error}</p>}
    <label className="ticket-search" htmlFor="ticket-search">Find a ticket<input id="ticket-search" type="search" dir="auto" value={ticketQuery} onChange={(event) => setTicketQuery(event.target.value)} placeholder="Search questions or ticket IDs…" /></label>
    {!loading && !error && ticketQuery && <p className="filter-summary" role="status">{visibleTickets.length} matching tickets in the selected status.</p>}
    <div className="dispatch-layout"><div className="ticket-list" aria-label="Support tickets">
      {loading ? <p role="status">Loading local tickets…</p> : visibleTickets.length === 0 ? <p className="ticket-empty">No matching tickets. Adjust the filters, or open a saved Oracle answer and choose Request human review.</p> : <><p className="ticket-count">{visibleTickets.length} tickets in this view</p>{visibleTickets.map((ticket) => <button key={ticket.id} disabled={working} className={`ticket-card ${selectedId === ticket.id ? 'selected' : ''}`} onClick={() => { selectedRef.current = ticket.id; setSelectedId(ticket.id); setNote(''); window.location.hash = `#dispatch?ticket=${ticket.id}` }} aria-pressed={selectedId === ticket.id}>
        <span className={`ticket-status ${ticket.status}`}>{statusLabel[ticket.status]}</span><span className="ticket-reference">#{ticket.id.slice(0,8)}</span><strong dir="auto">{ticket.question}</strong><span>{reasons[ticket.reason] ?? 'Human review required'}</span><small>{date(ticket.updated_at)} · Cairo</small>
      </button>)}</>}
    </div><div className="ticket-detail" aria-live="polite" aria-busy={working || detailLoading}>
      {detailLoading && <p role="status">Loading ticket…</p>}
      {detailError && <p className="library-error" role="alert">{detailError}</p>}
      {!selectedId && <div className="ticket-empty"><span aria-hidden="true">↗</span><h4>Select a ticket to review</h4><p>The saved question, escalation reason, supporting evidence, and local activity will appear here.</p></div>}
      {detail && <>
        <div className="ticket-detail-heading"><span className={`ticket-status ${detail.status}`}>{statusLabel[detail.status]}</span><span>#{detail.id.slice(0,8)} · revision {detail.revision}</span></div>
        <h4 className="ticket-question" dir="auto">{detail.question}</h4><p className="ticket-reason">{reasons[detail.reason] ?? 'Human review required'}</p>
        <p className="ticket-time">Created {date(detail.created_at)} · Cairo time</p>
        {detail.origin_available ? <a className="primary-link" href={`#oracle?conversation=${detail.conversation_id}`}>Open saved conversation →</a> : <p className="stale-citation">The original conversation was deleted. This ticket retains its own historical snapshot.</p>}
        <details className="oracle-details"><summary>Saved answer and evidence</summary><p>Answer status: {detail.snapshot.status} · model: {detail.snapshot.model}</p>{detail.snapshot.claims.length === 0 ? <p>No generated answer was accepted for this turn.</p> : detail.snapshot.claims.map((claim,index) => <div key={index}><p dir="auto">{claim.text}</p>{claim.evidence.map((item,i) => <blockquote key={i} className="ticket-quote"><span>{item.source_id}</span><p dir="auto">{item.quote}</p></blockquote>)}</div>)}
          <div className="oracle-citations">{detail.snapshot.sources.map((source) => source.citation_state === 'current' ? <a key={source.source_id} href={sourceLink(source.document_id,source.id,{start:source.start_char,end:source.end_char})}>[{source.source_id}] {source.filename}</a> : <span key={source.source_id} className="stale-citation">[{source.source_id}] {source.filename} · {source.citation_state}</span>)}</div><p>Quotes are saved evidence, not a guarantee of correctness. Reason code: {detail.reason}</p>
        </details>
        <form className="ticket-update" onSubmit={(event) => { event.preventDefault(); void save() }}>
          <label htmlFor="ticket-status">Status<select id="ticket-status" value={nextStatus} disabled={working} onChange={(event) => setNextStatus(event.target.value as TicketStatus)}>{Object.entries(statusLabel).map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label htmlFor="ticket-note">Internal note / resolution note</label><textarea id="ticket-note" dir="auto" value={note} maxLength={2000} disabled={working} onChange={(event) => setNote(event.target.value)} placeholder="Record the review, next action, or resolution. Required when resolving." />
          <div className="oracle-actions"><span>{note.length} / 2000 · Internal only</span><button className="gold-button" disabled={working || (nextStatus === detail.status && !note.trim()) || (nextStatus === 'resolved' && detail.status !== 'resolved' && !note.trim())}>{working ? 'Saving…' : 'Save ticket update'}</button></div>
        </form>
        {detail.resolution && <div className="ticket-resolution"><h4>Resolution</h4><p dir="auto">{detail.resolution}</p></div>}
        <h4 className="ticket-activity-title">Local activity</h4><ol className="ticket-events">{detail.events.map((event) => <li key={event.id}><span>{statusLabel[event.status]} · {date(event.created_at)} · Cairo</span><p dir="auto">{event.note || 'Status updated.'}</p></li>)}</ol>
        {confirmDelete ? <div className="conversation-delete" role="alert"><p>Delete this ticket, its saved question/evidence, and all activity? This cannot be undone.</p><button className="quiet-button" disabled={working} onClick={() => void remove()}>Confirm delete ticket</button><button className="quiet-button" disabled={working} onClick={() => setConfirmDelete(false)}>Cancel</button></div> : <button className="quiet-button ticket-delete" disabled={working} onClick={() => setConfirmDelete(true)}>Delete local ticket</button>}
      </>}
    </div></div>
  </section>
}
