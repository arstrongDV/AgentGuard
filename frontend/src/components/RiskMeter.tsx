import clsx from 'clsx'

const GATE = 0.3 // policy: risk above which the ML classifier runs
const BLOCK = 0.85 // policy: injection block threshold

/** 0–1 bar with ticks at the policy thresholds, so a number always has context. */
export function RiskMeter({ value, wide = false }: { value: number; wide?: boolean }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100)
  const fill = value >= BLOCK ? 'bg-fg' : value >= GATE ? 'bg-fg/70' : 'bg-muted/60'
  return (
    <span className="inline-flex items-center gap-2" title={`risk ${value.toFixed(2)} (gate ${GATE}, block ${BLOCK})`}>
      <span className={clsx('relative h-1.5 overflow-hidden rounded-full bg-line', wide ? 'w-40' : 'w-12')}>
        <span className={clsx('absolute inset-y-0 left-0 rounded-full', fill)} style={{ width: `${pct}%` }} />
        <span className="absolute inset-y-0 w-px bg-bg" style={{ left: `${GATE * 100}%` }} />
        <span className="absolute inset-y-0 w-px bg-bg" style={{ left: `${BLOCK * 100}%` }} />
      </span>
      <span className="tabular font-mono text-xs text-muted">{value.toFixed(2)}</span>
    </span>
  )
}
