// Align original and redacted text so the UI can show which value each placeholder replaced.
// The backend replaces values with placeholders like [EMAIL_1] and leaves everything else untouched,
// so walking the literal parts of the redacted text through the original recovers each value.

const PLACEHOLDER = /(\[(?:[A-Z]+_)+\d+\]|\[REMOVED_LINK\])/

export type Segment =
  | { kind: 'same'; text: string }
  | { kind: 'replaced'; placeholder: string; original: string }

export function alignRedaction(original: string, redacted: string): Segment[] | null {
  const parts = redacted.split(PLACEHOLDER) // literal, placeholder, literal, placeholder, ...
  const segments: Segment[] = []
  let cursor = 0
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i]
    if (i % 2 === 0) {
      if (original.slice(cursor, cursor + part.length) !== part) return null
      if (part) segments.push({ kind: 'same', text: part })
      cursor += part.length
      continue
    }
    const next = parts[i + 1] ?? ''
    if (next === '' && i + 2 < parts.length) return null // two adjacent placeholders: ambiguous
    const end = next === '' ? original.length : original.indexOf(next, cursor)
    if (end < 0) return null
    segments.push({ kind: 'replaced', placeholder: part, original: original.slice(cursor, end) })
    cursor = end
  }
  return cursor === original.length ? segments : null
}
