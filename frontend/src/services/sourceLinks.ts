export interface SourceRange { start: number; end: number }

export function sourceLink(documentId: string, sourceId?: string, range?: SourceRange): string {
  const parameters = new URLSearchParams({ document: documentId })
  if (sourceId) parameters.set('source', sourceId)
  if (range) { parameters.set('start', String(range.start)); parameters.set('end', String(range.end)) }
  return `#library?${parameters}`
}

export function readSourceSelection() {
  const parameters = new URLSearchParams(window.location.hash.split('?')[1] ?? '')
  const start = parameters.get('start'), end = parameters.get('end')
  const hasRange = start !== null || end !== null
  const valid = start !== null && end !== null && /^\d+$/.test(start) && /^\d+$/.test(end)
    && Number.isSafeInteger(Number(start)) && Number.isSafeInteger(Number(end)) && Number(start) < Number(end)
  return { documentId: parameters.get('document') || null, sourceId: parameters.get('source') || null,
    range: valid ? { start: Number(start), end: Number(end) } : null, invalidRange: hasRange && !valid }
}
