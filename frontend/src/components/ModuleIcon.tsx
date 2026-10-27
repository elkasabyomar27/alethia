export type ModuleName = 'oracle' | 'library' | 'tribunal' | 'dispatch'

/** Small, local line drawings; no icon font or external asset request. */
export default function ModuleIcon({ name, className = '' }: { name: ModuleName; className?: string }) {
  return <svg className={className} viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    {name === 'oracle' ? <><circle cx="16" cy="16" r="11" /><path d="M5 16s4-6 11-6 11 6 11 6-4 6-11 6S5 16 5 16Z" /><circle cx="16" cy="16" r="3" /><path d="M16 1v3m0 24v3M1 16h3m24 0h3" /></>
      : name === 'library' ? <><path d="m3 10 13-7 13 7H3Zm2 3h22M3 29h26M5 26h22M8 14v10m5-10v10m6-10v10m5-10v10" /><path d="M14 8h4" /></>
      : name === 'tribunal' ? <><path d="M16 4v23m-6 2h12M5 10h22M7 10 2 21h10L7 10Zm18 0-5 11h10l-5-11Z" /><circle cx="16" cy="6" r="2" /><path d="M2 21c1 5 9 5 10 0m8 0c1 5 9 5 10 0" /></>
      : <><path d="M5 26 24 7M13 10l14-5-3 14M12 15l-7 1 3-6 12-5M17 20l-1 7 6-3 5-12M7 22l3 3M4 29l3-3" /></>}
  </svg>
}
