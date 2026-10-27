import { useEffect, useRef, useState } from 'react'
import MythicArtwork, { moduleArtwork } from './components/MythicArtwork'
import ModuleIcon from './components/ModuleIcon'
import Library from './pages/Library'
import Oracle from './pages/Oracle'
import Dispatch from './pages/Dispatch'
import Tribunal from './pages/Tribunal'
import { checkBackend, type BackendState } from './services/api'

const modules = [
  { id: 'oracle', symbol: '☉', name: 'The Oracle', label: 'AI customer support', phase: '03', description: 'Turn your business knowledge into clear, grounded answers. Every answer begins with evidence.' },
  { id: 'library', symbol: '▥', name: "Athena’s Library", label: 'Knowledge management', phase: '02', description: 'A home for your company’s knowledge. Bring your policies, products, and procedures into one searchable collection.' },
  { id: 'tribunal', symbol: '⚖', name: "Themis’ Tribunal", label: 'Evaluation laboratory', phase: '05', description: 'Put every answer to the test. Compare retrieval methods and examine quality across languages with reproducible evidence.' },
  { id: 'dispatch', symbol: '↗', name: "Hermes’ Dispatch", label: 'Human handoff', phase: '04', description: 'When knowledge reaches its limits, bring in a person. Keep unanswered questions and their context together.' },
] as const
type ModuleId = typeof modules[number]['id']
const readRoute = (): ModuleId => modules.find((m) => `#${m.id}` === window.location.hash.split('?')[0])?.id ?? 'oracle'

export default function App() {
  const [active, setActive] = useState<ModuleId>(readRoute)
  const [backend, setBackend] = useState<BackendState>('checking')
  const [attempt, setAttempt] = useState(0)
  const heading = useRef<HTMLHeadingElement>(null)
  const previousModule = useRef(active)
  const current = modules.find((m) => m.id === active)!

  useEffect(() => {
    const navigate = () => {
      if (!modules.some((m) => `#${m.id}` === window.location.hash.split('?')[0])) return
      setActive(readRoute())
    }
    window.addEventListener('hashchange', navigate)
    return () => window.removeEventListener('hashchange', navigate)
  }, [])

  useEffect(() => {
    if (previousModule.current === active) return
    previousModule.current = active
    heading.current?.focus({ preventScroll: true })
    window.scrollTo({ top: 0, behavior: 'instant' })
  }, [active])

  useEffect(() => {
    const controller = new AbortController()
    let live = true
    setBackend('checking')
    const timeout = window.setTimeout(() => controller.abort(), 5000)
    checkBackend(controller.signal).then(() => { if (live) setBackend('online') })
      .catch(() => { if (live) setBackend('offline') })
      .finally(() => window.clearTimeout(timeout))
    return () => { live = false; controller.abort(); window.clearTimeout(timeout) }
  }, [attempt])

  return (
    <div className="app-shell sanctuary-shell" data-module={active}>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className="sidebar">
        <a className="brand" href="#oracle" aria-label="ALETHIA home"><span className="brand-mark">Α</span><span>ALETHIA<small>Α Λ Η Θ Ε Ι Α</small></span></a>
        <div className="sidebar-rule" />
        <p className="eyebrow nav-caption">THE SANCTUARY</p>
        <nav aria-label="Main navigation">
          {modules.map((m) => <a key={m.id} href={`#${m.id}`} className={`nav-link ${active === m.id ? 'active' : ''}`} aria-current={active === m.id ? 'page' : undefined}>
            <ModuleIcon name={m.id} className="nav-icon" /><span>{m.name}<small>{m.label}</small></span>
          </a>)}
        </nav>
        <div className="sidebar-bottom"><span className="small-seal" aria-hidden="true">✧</span><p>Knowledge is the foundation.<br />Truth is the destination.</p><span className="eyebrow">TRACEABLE ANSWERS · SOURCE FIRST</span></div>
      </aside>

      <div className="workspace">
        <header className="topbar"><span>YOUR SANCTUARY <span className="breadcrumb">/ {current.label}</span></span><div className="connection" role="status"><span className={`status-dot ${backend}`} />{backend === 'online' ? 'Local API connected' : backend === 'offline' ? 'Local API unavailable' : 'Connecting…'}<button onClick={() => setAttempt((n) => n + 1)} disabled={backend === 'checking'} aria-label="Recheck local API connection">↻</button></div></header>
        <main id="main-content" tabIndex={-1}>
          <section className="module-header" aria-labelledby="page-heading">
            <MythicArtwork module={active} />
            <div className="module-copy"><p className="eyebrow text-gold">{current.label}</p><h1 ref={heading} tabIndex={-1} id="page-heading">{current.name}</h1><p>{current.description}</p></div>
            <div className="module-crest"><ModuleIcon name={active} /><span>ΑΛΗΘΕΙΑ</span></div>
          </section>

          <div className="content-area">
            <div hidden={active !== 'oracle'}><Oracle /></div>
            {active === 'library' ? <Library /> : active === 'dispatch' ? <Dispatch /> : active === 'tribunal' ? <Tribunal /> : null}

            <section className="sanctuary-coda" aria-label="The spirit of ALETHIA">
              <MythicArtwork module={active} closing />
              <div><p className="eyebrow">KNOWLEDGE THROUGH THE AGES</p><p className="coda-title">A timeless pursuit.<br /><em>A clearer answer.</em></p><span>ΑΛΗΘΕΙΑ · TRUTH, BROUGHT TO LIGHT</span></div>
            </section>
            <footer className="workspace-footer"><span>ALETHIA <span className="footer-dot">·</span> Where Knowledge Becomes Answers.</span><details className="art-credits"><summary>Artwork credits</summary><p>Public-domain engraving: <a href={`https://commons.wikimedia.org/wiki/File:${moduleArtwork[active].source}`} target="_blank" rel="noreferrer">{moduleArtwork[active].name} · {active === 'library' ? '1851' : '1878'}</a>. Displayed with CSS tinting and cropping.</p></details></footer>
          </div>
        </main>
      </div>
    </div>
  )
}
