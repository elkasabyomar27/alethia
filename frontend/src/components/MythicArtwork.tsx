import { useEffect, useRef } from 'react'
import type { ModuleName } from './ModuleIcon'

export const moduleArtwork = {
  oracle: { name: 'Apollo', file: 'apollo-1878.jpg', width: 624, height: 900, source: 'Apollo_-_the_Greek_god_of_the_Light,_the_Healing,_and_the_Spring.jpg' },
  library: { name: 'Athena', file: 'athena-1851.jpg', width: 437, height: 900, source: 'Statue_of_Pallas_Athena_Engraving_Illustration_id465487203.jpg' },
  tribunal: { name: 'Themis', file: 'themis-1878.jpg', width: 900, height: 900, source: 'Themis_-_the_ancient_Greek_Titaness.jpg' },
  dispatch: { name: 'Hermes', file: 'hermes-1878.jpg', width: 633, height: 900, source: 'Hermes_-_the_Greek_god_of_transitions_and_boundaries.jpg' },
} satisfies Record<ModuleName, { name: string; file: string; width: number; height: number; source: string }>

/** Decorative layers move only on scroll; no animation loop or React scroll renders. */
export default function MythicArtwork({ module, closing = false }: { module: ModuleName; closing?: boolean }) {
  const artwork = moduleArtwork[module]
  const scene = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const element = scene.current
    if (!element) return
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)')
    let frame = 0
    let visible = true
    const update = () => {
      frame = 0
      if (preference.matches) { element.style.setProperty('--drift', '0px'); return }
      const rect = element.getBoundingClientRect()
      const distance = Math.max(-45, Math.min(45, (window.innerHeight * .35 - rect.top) * .09))
      element.style.setProperty('--drift', `${distance}px`)
    }
    const schedule = () => { if (visible && !frame) frame = requestAnimationFrame(update) }
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting
      if (visible) { element.classList.add('art-entered'); schedule() }
    }, { rootMargin: '60px' })
    observer.observe(element)
    window.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', schedule, { passive: true })
    preference.addEventListener('change', update)
    update()
    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      window.removeEventListener('scroll', schedule)
      window.removeEventListener('resize', schedule)
      preference.removeEventListener('change', update)
    }
  }, [])
  return <div ref={scene} className={`mythic-art art-${module} ${closing ? 'mythic-art-closing' : ''}`} aria-hidden="true">
    <div className="art-orbit" />
    <div className="art-orbit art-orbit-inner" />
    <div className="art-figure-motion"><img key={artwork.file} className="art-athena" src={`/art/${artwork.file}`} alt="" width={artwork.width} height={artwork.height} decoding="async" loading={closing ? 'lazy' : 'eager'} /></div>
    <span className="art-star art-star-one">✧</span><span className="art-star art-star-two">✦</span>
    <div className="art-horizon" />
  </div>
}
