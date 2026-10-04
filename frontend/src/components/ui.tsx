import clsx from 'clsx'
import type { ReactNode } from 'react'

export function Card({ title, subtitle, actions, children, className }: {
  title?: string
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={clsx('rounded-lg border border-line bg-surface p-4', className)}>
      {(title || actions) && (
        <header className="mb-3 flex flex-wrap items-start gap-2">
          <div className="min-w-0 flex-1">
            {title && <h2 className="text-sm font-semibold">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}

/** Label · big value · optional hint. Values are proportional figures at display size (no tabular-nums). */
export function StatTile({ label, value, hint, tone = 'fg' }: { label: string; value: ReactNode; hint?: ReactNode; tone?: 'fg' | 'block' | 'redact' | 'accent' }) {
  const color = { fg: 'text-fg', block: 'text-block', redact: 'text-redact', accent: 'text-accent' }[tone]
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3">
      <p className="text-xs text-muted">{label}</p>
      <p className={clsx('mt-1 text-3xl font-semibold tracking-tight', color)}>{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  )
}

export function Segmented<T extends string>({ value, options, onChange, disabled, size = 'sm', label }: {
  value: T
  options: { value: T; label: string; title?: string }[]
  onChange: (value: T) => void
  disabled?: boolean
  size?: 'sm' | 'md'
  label: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className={clsx('inline-flex rounded-md border border-line bg-bg p-0.5', disabled && 'opacity-60')}>
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={o.value === value}
          title={o.title}
          disabled={disabled}
          onClick={() => o.value !== value && onChange(o.value)}
          className={clsx(
            'rounded px-2.5 transition-colors',
            size === 'sm' ? 'py-1 text-xs' : 'py-1.5 text-sm',
            o.value === value ? 'bg-surface-2 font-medium text-fg shadow-sm' : 'text-muted hover:text-fg',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/** Progress against a limit: accent, amber from 80 %, red at the limit (budgets end in a block). */
export function Meter({ value, limit, label, format }: { value: number; limit: number | null; label: string; format: (n: number) => string }) {
  const fraction = limit ? value / limit : 0
  const fill = !limit ? 'bg-muted/50' : fraction >= 1 ? 'bg-block' : fraction >= 0.8 ? 'bg-redact' : 'bg-accent'
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2 text-xs">
        <span className="text-muted">{label}</span>
        <span className="tabular font-mono">
          {format(value)} <span className="text-muted">/ {limit === null ? 'no limit' : format(limit)}</span>
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-line" role="meter" aria-label={label} aria-valuenow={value} aria-valuemax={limit ?? undefined}>
        <div className={clsx('h-full rounded-full transition-[width]', fill)} style={{ width: `${limit ? Math.min(100, fraction * 100) : 0}%` }} />
      </div>
      {limit !== null && fraction >= 1 && <p className="mt-1 text-xs text-block">Limit reached: new requests are blocked until the reset.</p>}
    </div>
  )
}

export function Chip({ children, tone = 'neutral', title }: { children: ReactNode; tone?: 'neutral' | 'approval' | 'accent'; title?: string }) {
  const style = {
    neutral: 'border-line bg-surface-2 text-fg',
    approval: 'border-approval/40 bg-approval/10 text-approval',
    accent: 'border-accent/40 bg-accent/10 text-accent',
  }[tone]
  return (
    <span title={title} className={clsx('inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[11px]', style)}>
      {children}
    </span>
  )
}

export function WindowPicker<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: T[] }) {
  return <Segmented label="Time window" value={value} onChange={onChange} options={options.map((o) => ({ value: o, label: o }))} />
}
