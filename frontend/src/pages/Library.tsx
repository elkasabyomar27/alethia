import { useEffect, useRef, useState } from 'react'
import { getDocument, importDemoPack, listDocuments, removeDocument, saveDocument,
  type DocumentDetail, type DocumentMetadata } from '../services/api'
import SearchInspector from '../components/SearchInspector'
import { readSourceSelection, sourceLink, type SourceRange } from '../services/sourceLinks'

const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Something went wrong. Please retry.'
const fileSize = (size: number) => size < 1024 ? `${size} B` : `${(size / 1024).toFixed(1)} KiB`

export default function Library() {
  const [documents, setDocuments] = useState<DocumentMetadata[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(() => readSourceSelection().documentId)
  const [sourceId, setSourceId] = useState<string | null>(() => readSourceSelection().sourceId)
  const [sourceRange, setSourceRange] = useState<SourceRange | null>(() => readSourceSelection().range)
  const [invalidRange, setInvalidRange] = useState(() => readSourceSelection().invalidRange)
  const [detail, setDetail] = useState<DocumentDetail | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [listError, setListError] = useState('')
  const [detailError, setDetailError] = useState('')
  const [actionError, setActionError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [sourceRefresh, setSourceRefresh] = useState(0)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [view, setView] = useState<'segments' | 'text'>('segments')
  const [documentFilter, setDocumentFilter] = useState('')
  const [documentSort, setDocumentSort] = useState<'recent' | 'name'>('recent')
  const visibleDocuments = documents.filter((item) => item.filename.toLocaleLowerCase().includes(documentFilter.trim().toLocaleLowerCase()))
    .sort((a, b) => documentSort === 'name' ? a.filename.localeCompare(b.filename) : b.updated_at.localeCompare(a.updated_at))
  const uploadInput = useRef<HTMLInputElement>(null)
  const replaceInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const navigate = () => {
      if (window.location.hash.split('?')[0] !== '#library') return
      const selection = readSourceSelection()
      setSelectedId(selection.documentId ?? documents[0]?.id ?? null)
      setSourceId(selection.sourceId)
      setSourceRange(selection.range)
      setInvalidRange(selection.invalidRange)
      setView('segments')
      setSourceRefresh((n) => n + 1)
    }
    window.addEventListener('hashchange', navigate)
    return () => window.removeEventListener('hashchange', navigate)
  }, [documents])

  useEffect(() => {
    const controller = new AbortController()
    let live = true
    setLoading(true)
    setListError('')
    listDocuments(controller.signal).then((items) => {
      if (!live) return
      setDocuments(items)
      const requested = readSourceSelection().documentId
      setSelectedId((previous) => requested ?? (items.some((item) => item.id === previous) ? previous : items[0]?.id ?? null))
    }).catch((error) => { if (live) setListError(errorMessage(error)) })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false; controller.abort() }
  }, [refresh])

  useEffect(() => {
    setDetail(null)
    setDetailError('')
    setConfirmDelete(false)
    if (!selectedId) { setDetailLoading(false); return }
    const controller = new AbortController()
    let live = true
    setDetailLoading(true)
    getDocument(selectedId, controller.signal).then((document) => { if (live) setDetail(document) })
      .catch((error) => {
        if (!live) return
        const message = errorMessage(error)
        setDetailError(message === 'Document not found.' ? `${message} It may have been deleted. Run the search again.` : message)
      })
      .finally(() => { if (live) setDetailLoading(false) })
    return () => { live = false; controller.abort() }
  }, [selectedId, refresh, sourceRefresh])

  useEffect(() => {
    if (!detail || detail.id !== selectedId || !sourceId || view !== 'segments') return
    const frame = window.requestAnimationFrame(() => {
      const element = document.getElementById(`source-${sourceId}`)
      element?.focus({ preventScroll: true })
      element?.scrollIntoView({ block: 'center', behavior: 'auto' })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [detail, selectedId, sourceId, view])

  function selectDocument(documentId: string) {
    setSelectedId(documentId)
    setSourceId(null)
    setSourceRange(null)
    setInvalidRange(false)
    window.location.hash = sourceLink(documentId)
  }

  function revalidateSameSource(documentId: string, selectedSourceId: string, range?: SourceRange) {
    // Hash navigation revalidates changed URLs. Identical URLs do not emit hashchange.
    if (window.location.hash === sourceLink(documentId, selectedSourceId, range)) setSourceRefresh((n) => n + 1)
  }

  async function action(operation: () => Promise<void>) {
    setBusy(true)
    setActionError('')
    setNotice('')
    try { await operation(); setRefresh((n) => n + 1) }
    catch (error) { setActionError(errorMessage(error)) }
    finally { setBusy(false) }
  }

  async function upload(selectedFile: File, replaceId?: string) {
    await action(async () => {
      if (!/\.(txt|md|markdown|pdf|docx)$/i.test(selectedFile.name)) throw new Error('Choose a PDF, DOCX, UTF-8 TXT, or Markdown file. Legacy DOC is not supported.')
      if (selectedFile.size > 1024 * 1024) throw new Error('File exceeds the 1 MiB upload limit.')
      const result = await saveDocument(selectedFile, replaceId)
      selectDocument(result.document.id)
      setNotice(result.outcome === 'duplicate' ? `Already in your library: ${result.document.filename}. No duplicate was created.`
        : result.outcome === 'updated' ? `Replaced ${result.document.filename}. Revision ${result.document.revision} is stored.`
          : `Added ${result.document.filename} to your library.`)
      setFile(null)
      if (uploadInput.current) uploadInput.current.value = ''
    })
  }

  return (
    <div className="library">
      <section className="library-intake" aria-labelledby="intake-heading">
        <div><p className="eyebrow text-gold">BRING KNOWLEDGE INTO THE SANCTUARY</p><h2 id="intake-heading">Every answer begins with a source.</h2><p>Store PDF, DOCX, UTF-8 TXT, and Markdown documents locally. Text-based files only; scanned pages and images are not OCR processed.</p></div>
        <form onSubmit={(event) => { event.preventDefault(); if (file) void upload(file) }}>
          <label htmlFor="document-upload">Choose a document <span>Up to 1 MiB · TXT/MD in UTF-8</span></label>
          <div className="upload-controls"><input ref={uploadInput} id="document-upload" type="file" accept=".pdf,.docx,.txt,.md,.markdown" disabled={busy} onChange={(event) => setFile(event.target.files?.[0] ?? null)} /><button className="gold-button" type="submit" disabled={busy || !file}>{busy ? 'Working…' : 'Add to library'}</button></div>
        </form>
        <div className="demo-row"><p>Start with Helios Home: six fictional English/Arabic e-commerce documents.</p><button className="quiet-button" disabled={busy} onClick={() => void action(async () => {
          const results = await importDemoPack()
          const added = results.filter((result) => result.outcome === 'created').length
          if (results[0]) selectDocument(results[0].document.id)
          setNotice(`Demo pack: ${added} added, ${results.length - added} already present. All policies are fictional.`)
        })}>Load fictional demo pack <span aria-hidden="true">↓</span></button></div>
      </section>

      {notice && <p className="library-notice" role="status">{notice}</p>}
      {busy && <p className="operation-status" role="status"><progress aria-label="Document operation in progress" />Processing your document operation locally. Please wait…</p>}
      {actionError && <p className="library-error" role="alert">{actionError}</p>}
      <SearchInspector libraryRevision={refresh} onInspectSource={revalidateSameSource} />
      <div className="library-toolbar"><p>{listError ? 'Collection unavailable' : <><strong>{loading ? '…' : documents.length}</strong> documents stored</>}<span>· Inspect original source text below</span></p><button className="quiet-button" onClick={() => setRefresh((n) => n + 1)} disabled={busy || loading}>Refresh library</button></div>
      {listError && <p className="library-error" role="alert">{listError}</p>}

      <div className="library-grid" aria-busy={loading || busy}>
        <section className="document-collection" aria-label="Stored documents">
          <h3>Library collection</h3>
          <div className="collection-filters"><label htmlFor="document-filter">Find a document<input id="document-filter" type="search" dir="auto" value={documentFilter} onChange={(event) => setDocumentFilter(event.target.value)} placeholder="Filter by filename…" /></label><label htmlFor="document-sort">Sort<select id="document-sort" value={documentSort} onChange={(event) => setDocumentSort(event.target.value as typeof documentSort)}><option value="recent">Recently updated</option><option value="name">Filename A–Z</option></select></label></div>
          {!loading && !listError && documents.length > 0 && <p className="filter-summary" role="status">{visibleDocuments.length} of {documents.length} documents{visibleDocuments.length === 0 ? ' · No matching filenames.' : ''}</p>}
          {loading && <p className="library-hint" role="status">Reading the local collection…</p>}
          {!loading && !listError && documents.length === 0 && <p className="library-hint">Your first chapter is waiting. Upload a document or load the fictional demo pack.</p>}
          <ul>{visibleDocuments.map((document) => <li key={document.id}><button className={`document-row ${selectedId === document.id ? 'selected' : ''}`} aria-pressed={selectedId === document.id} disabled={busy} onClick={() => selectDocument(document.id)}><span className="document-type" aria-hidden="true">{document.format === 'markdown' ? 'MD' : document.format.toUpperCase()}</span><span className="document-label"><b dir="auto">{document.filename}</b><small>{document.segment_count} source segments · {fileSize(document.size_bytes)} · v{document.revision}{document.page_count !== null ? ` · ${document.page_count} pages` : ''}{document.warnings.length > 0 ? ' · Review notes' : ''}</small></span><span aria-hidden="true">›</span></button></li>)}</ul>
        </section>

        <section className="document-inspector" aria-labelledby="inspector-heading" aria-busy={detailLoading}>
          <div className="inspector-heading"><p className="eyebrow text-gold">SOURCE INSPECTOR</p><span className="storage-badge">LOCAL STORAGE</span></div>
          <h3 id="inspector-heading" dir="auto">{detail?.filename ?? (detailLoading ? 'Opening document…' : 'Select a document')}</h3>
          {detailError && <p className="library-error" role="alert">{detailError}</p>}
          {!detail && !detailLoading && !detailError && <p className="library-hint">Inspect extracted text, section references, and document metadata here.</p>}
          {detail && <>
            <dl className="document-metadata"><div><dt>Source segments</dt><dd>{detail.segment_count}</dd></div><div><dt>Characters</dt><dd>{detail.character_count.toLocaleString()}</dd></div><div><dt>Revision</dt><dd>{detail.revision}</dd></div><div><dt>Updated</dt><dd>{new Date(detail.updated_at).toLocaleDateString()}</dd></div></dl>
            <details className="source-identifiers"><summary>Document identity and processing details</summary><dl><dt>Document ID</dt><dd>{detail.id}</dd><dt>Content identity SHA-256 ({detail.hash_basis === 'original_file_bytes' ? 'original file bytes' : 'normalized text'})</dt><dd>{detail.content_hash}</dd><dt>Processor</dt><dd>{detail.processor_version}</dd>{detail.page_count !== null && <><dt>Physical PDF pages (including pages without text)</dt><dd>{detail.page_count}</dd></>}</dl></details>
            {detail.warnings.length > 0 && <aside className="extraction-notes" aria-label="Extraction review notes"><p className="eyebrow">REVIEW THE EXTRACTED SOURCE</p><ul>{detail.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></aside>}
            <p className="inspector-note">Original source references remain stable. Encoder search links highlight the exact retrieved span inside its parent source.</p>
            {invalidRange && <p className="library-error" role="alert">This source link contains an invalid text range. Run the search again.</p>}
            {sourceId && detail.id === selectedId && !detail.segments.some((segment) => segment.id === sourceId) && <p className="library-error" role="alert">This source is no longer part of the document. It may have been replaced. Run the search again.</p>}
            <div className="inspector-controls"><div className="view-buttons" role="group" aria-label="Source view"><button className={view === 'segments' ? 'chosen' : ''} aria-pressed={view === 'segments'} onClick={() => setView('segments')}>Source segments</button><button className={view === 'text' ? 'chosen' : ''} aria-pressed={view === 'text'} onClick={() => setView('text')}>Full text</button></div><button className="quiet-button" disabled={busy} onClick={() => replaceInput.current?.click()}>Replace document</button><input ref={replaceInput} type="file" hidden accept=".pdf,.docx,.txt,.md,.markdown" onChange={(event) => { const replacement = event.target.files?.[0]; event.target.value = ''; if (replacement) void upload(replacement, detail.id) }} /></div>
            <div className="source-content" role="region" aria-label="Document source content" tabIndex={0} key={`${detail.id}-${view}`}>
              {view === 'text' ? <pre className="source-text" dir="auto">{detail.text}</pre> : detail.segments.map((segment) => {
                const selected = sourceId === segment.id
                const rangeValid = sourceRange && sourceRange.start >= segment.start_char && sourceRange.end <= segment.end_char
                const first = rangeValid && sourceRange ? sourceRange.start - segment.start_char : 0
                const last = rangeValid && sourceRange ? sourceRange.end - segment.start_char : 0
                const characters = Array.from(segment.text)
                return <article className={`source-segment ${selected ? 'selected-source' : ''}`} tabIndex={-1} key={segment.id} id={`source-${segment.id}`}><div><h4 dir="auto">{segment.section}</h4><span>{segment.source_label ?? `Lines ${segment.start_line}–${segment.end_line}`}</span></div>{selected && sourceRange && !rangeValid && <p className="library-error" role="alert">The linked text range is no longer available. Run the search again.</p>}<pre className="source-text" dir="auto">{selected && rangeValid ? <>{characters.slice(0, first).join('')}<mark className="source-span">{characters.slice(first, last).join('')}</mark>{characters.slice(last).join('')}</> : segment.text}</pre><details><summary>Source reference</summary><code>{segment.id}</code>{segment.page_number !== null && <p>Physical PDF page {segment.page_number}</p>}<p>Extracted text lines {segment.start_line}–{segment.end_line}</p><p>Characters {segment.start_char}–{segment.end_char} (end exclusive)</p><a href={sourceLink(detail.id, segment.id)} className="source-permalink" onClick={() => revalidateSameSource(detail.id, segment.id)}>Link to this source</a></details></article>
              })}
            </div>
            <div className="delete-area">{confirmDelete ? <><p>Delete <b dir="auto">{detail.filename}</b> and its stored source segments? This cannot be undone.</p><div><button className="danger-button" disabled={busy} onClick={() => void action(async () => { await removeDocument(detail.id); setDetail(null); setSelectedId(null); setSourceId(null); window.location.hash = '#library'; setConfirmDelete(false); setNotice(`Deleted ${detail.filename} and its source segments.`) })}>Confirm deletion</button><button className="quiet-button" disabled={busy} onClick={() => setConfirmDelete(false)}>Keep document</button></div></> : <button className="quiet-button delete-trigger" disabled={busy} onClick={() => setConfirmDelete(true)}>Delete document</button>}</div>
          </>}
        </section>
      </div>
    </div>
  )
}
