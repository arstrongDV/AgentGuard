import clsx from 'clsx'

const PLACEHOLDER = /(\[(?:[A-Z]+_)+\d+\]|\[REMOVED_LINK\])/

/** Pretty JSON in mono; redaction placeholders are highlighted so you can spot them at a glance. */
export function JsonView({ value, className }: { value: unknown; className?: string }) {
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2)
  return (
    <pre
      className={clsx(
        'max-h-80 overflow-auto rounded-md border border-line bg-bg p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap break-all',
        className,
      )}
    >
      {text.split(PLACEHOLDER).map((part, i) =>
        i % 2 === 1 ? (
          <mark key={i} className="rounded bg-redact/15 px-0.5 text-redact">
            {part}
          </mark>
        ) : (
          part
        ),
      )}
    </pre>
  )
}
