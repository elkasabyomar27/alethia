import { useEffect, useState } from 'react'
import { buildDenseIndex, getDenseStatus, type DenseStatus } from '../services/api'

export default function DensePanel({ revision, onStatus }: { revision: string; onStatus: (value: DenseStatus) => void }) {
  const [status, setStatus] = useState<DenseStatus | null>(null)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [starting, setStarting] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    let live = true
    let timer: number | undefined
    const poll = async () => {
      try {
        const next = await getDenseStatus(controller.signal)
        if (!live) return
        setStatus(next)
        onStatus(next)
        setError('')
        if (next.state === 'building') timer = window.setTimeout(() => void poll(), 1000)
      } catch (reason) {
        if (live) setError(reason instanceof Error ? reason.message : 'Encoder status is unavailable.')
      }
    }
    void poll()
    return () => { live = false; controller.abort(); window.clearTimeout(timer) }
  }, [revision, refresh, onStatus])

  async function build() {
    setStarting(true)
    setError('')
    try {
      const next = await buildDenseIndex()
      setStatus(next)
      onStatus(next)
      setRefresh((value) => value + 1)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Build failed.') }
    finally { setStarting(false) }
  }

  const building = status?.state === 'building'
  const snapshot = status?.snapshot
  const message = !status ? 'Checking the local encoder…' : status.state === 'ready'
    ? `${snapshot?.chunk_count ?? 0} encoder-aware chunks ready for BM25, semantic, and hybrid search.`
    : status.state === 'stale' ? 'The library changed. Rebuild the encoder snapshot before using its search modes.'
      : status.state === 'building' ? `Building locally · ${status.job?.stage ?? 'starting'}`
        : status.state === 'unavailable' ? 'The optional local model/runtime has not been prepared. Follow the project setup instructions.'
          : status.state === 'failed' ? status.last_error ?? 'The last encoder build failed. Check resources and retry.'
            : 'Build the encoder snapshot to enable semantic search and a matching BM25 chunk corpus.'

  return <aside className="dense-panel" aria-labelledby="dense-heading">
    <div><p className="eyebrow text-gold">MULTILINGUAL · LOCAL CPU INFERENCE</p><h4 id="dense-heading">Encoder-aware knowledge</h4><p className="dense-message" role="status">{message}</p>
      {building && status.job && status.job.total > 0 && <div className="dense-progress"><progress value={status.job.completed} max={status.job.total} /><span>{status.job.completed} / {status.job.total} · {status.job.stage}</span></div>}
    </div><button className="quiet-button" onClick={() => void build()} disabled={starting || building || !status?.runtime_available}>{starting ? 'Starting…' : building ? 'Building…' : snapshot ? 'Rebuild encoder index' : 'Build encoder index'}</button>
    {error && <p className="library-error dense-error" role="alert">{error}</p>}
    {status?.state === 'ready' && status.last_error && <p className="library-error dense-error" role="alert">The last rebuild failed; the previous snapshot is still available. {status.last_error}</p>}
    {status && <details className="dense-details"><summary>Model and resource details</summary><p>{status.model_id} · INT8 ONNX · {status.dimension} dimensions · CPU only</p><p>Revision: <code>{status.model_revision}</code></p><p>Passage budget: {status.passage_token_limit} tokens including prefix/special tokens. Worker cap: {status.worker_memory_limit_mib} MiB. Available RAM at last check: {(status.available_memory_mib / 1024).toFixed(2)} GiB.</p>{snapshot && <><p>Chunk corpus: <code>{snapshot.corpus_hash}</code></p><p>Last build: {snapshot.build_diagnostics.elapsed_seconds.toFixed(2)} seconds; peak worker RSS: {snapshot.build_diagnostics.memory.peak_rss_mib?.toFixed(1) ?? 'unavailable'} MiB. These are build diagnostics, not quality scores.</p></>}<p>Workers unload after each operation. A semantic query includes model startup time. Queries and evidence remain local.</p></details>}
  </aside>
}
