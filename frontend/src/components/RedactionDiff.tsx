import type { ReactNode } from 'react'
import { alignRedaction } from '../lib/diff'

/** Original (audit only) next to what was actually forwarded, with each replaced value lined up. */
export function RedactionDiff({ original, redacted }: { original: string; redacted: string }) {
  if (original === redacted) {
    return (
      <div>
        <Label>Content (unchanged)</Label>
        <Text>{original || <span className="text-muted italic">no text content</span>}</Text>
      </div>
    )
  }
  const segments = alignRedaction(original, redacted)
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <div>
        <Label>Original · stored in the audit log only</Label>
        <Text>
          {segments
            ? segments.map((s, i) =>
                s.kind === 'same' ? (
                  s.text
                ) : (
                  <mark key={i} className="rounded bg-block/20 px-0.5 text-fg line-through decoration-block/70">
                    {s.original}
                  </mark>
                ),
              )
            : original}
        </Text>
      </div>
      <div>
        <Label>Forwarded · what the model / agent received</Label>
        <Text>
          {segments
            ? segments.map((s, i) =>
                s.kind === 'same' ? (
                  s.text
                ) : (
                  <mark key={i} className="rounded bg-redact/15 px-0.5 font-mono text-redact" title={`replaced: ${s.original}`}>
                    {s.placeholder}
                  </mark>
                ),
              )
            : redacted}
        </Text>
      </div>
    </div>
  )
}

function Label({ children }: { children: ReactNode }) {
  return <p className="mb-1.5 text-xs text-muted">{children}</p>
}

function Text({ children }: { children: ReactNode }) {
  return (
    <div className="max-h-72 overflow-auto rounded-md border border-line bg-bg p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap break-words">
      {children}
    </div>
  )
}
