/** Local vector artwork: no external fonts, images, or image service. */
export default function Temple() {
  return (
    <svg className="temple" viewBox="0 0 900 440" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="stone" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#c5b792" /><stop offset=".5" stopColor="#5c646d" /><stop offset="1" stopColor="#172434" /></linearGradient>
        <linearGradient id="pillar"><stop stopColor="#202e3c" /><stop offset=".4" stopColor="#8b8b80" /><stop offset=".6" stopColor="#3b4854" /><stop offset="1" stopColor="#142030" /></linearGradient>
        <radialGradient id="aura"><stop stopColor="#c29b59" stopOpacity=".25" /><stop offset="1" stopColor="#c29b59" stopOpacity="0" /></radialGradient>
      </defs>
      <ellipse cx="515" cy="218" rx="330" ry="220" fill="url(#aura)" />
      <circle cx="520" cy="148" r="105" stroke="#bba471" strokeOpacity=".15" />
      <circle cx="520" cy="148" r="119" stroke="#bba471" strokeOpacity=".08" />
      <path d="M165 199 516 48 866 199Z" fill="url(#stone)" stroke="#c6b584" strokeOpacity=".5" />
      <path d="M221 185 516 72 811 185Z" fill="#13202d" stroke="#9c8d6e" />
      <path d="m489 151 27-44 27 44-27-12Z" stroke="#c4a565" strokeWidth="2" />
      <path d="M173 200H858V219H173Z" fill="url(#stone)" />
      {[215, 320, 425, 530, 635, 740].map((x) => <g key={x}>
        <path d={`M${x} 224h59v12h-59z M${x + 7} 355h45v11h-45z`} fill="url(#stone)" />
        <path d={`M${x + 10} 237h39l5 118h-49z`} fill="url(#pillar)" />
        {[18, 28, 38].map((d) => <path key={d} d={`M${x + d} 244v103`} stroke="#b6ac91" strokeOpacity=".2" />)}
      </g>)}
      <path d="M185 369H848V382H185Z M161 386H872V399H161Z M135 403H898V416H135Z" fill="url(#stone)" />
      <path d="M90 430H900" stroke="#b6a279" strokeOpacity=".3" />
    </svg>
  )
}
