import clsx from 'clsx'
import { ms } from '../lib/format'
import type { CheckTiming } from '../types/api'

const TIER_NAME: Record<number, string> = { 0: 'T0 gates', 1: 'T1 rules', 2: 'T2 classifier', 3: 'T3 judge' }

/**
 * Every check that looked at this event, grouped by tier, with its latency.
 * Skipped checks stay visible with the reason: that is the "cheap checks first, AI only when needed" story.
 */
export function PipelineTimeline({ timings, totalMs, upstreamMs }: { timings: CheckTiming[]; totalMs: number; upstreamMs?: number | null }) {
  if (timings.length === 0) return <p className="text-sm text-muted">No checks ran for this event.</p>
  const max = Math.max(...timings.map((t) => t.ms), 0.001)
  const tiers = [...new Set(timings.map((t) => t.tier))].sort()
  return (
    <div className="space-y-3">
      {tiers.map((tier) => (
        <div key={tier}>
          <p className="mb-1 text-[11px] font-medium tracking-wide text-muted uppercase">{TIER_NAME[tier] ?? `T${tier}`}</p>
          <ul className="space-y-1">
            {timings
              .filter((t) => t.tier === tier)
              .map((t) => (
                <li key={t.check} className="grid grid-cols-[8rem_1fr_4.5rem] items-center gap-2 text-xs">
                  <span className={clsx('truncate font-mono', t.skipped_reason ? 'text-muted/60' : 'text-fg')}>{t.check}</span>
                  {t.skipped_reason ? (
                    <span className="truncate text-muted/60 italic">skipped: {t.skipped_reason}</span>
                  ) : (
                    <span className="h-2 rounded-full bg-line">
                      <span className="block h-2 rounded-full bg-accent" style={{ width: `${Math.max(2, (t.ms / max) * 100)}%` }} />
                    </span>
                  )}
                  <span className="tabular text-right font-mono text-muted">{t.skipped_reason ? '–' : ms(t.ms)}</span>
                </li>
              ))}
          </ul>
        </div>
      ))}
      <p className="tabular border-t border-line pt-2 text-xs text-muted">
        AgentGuard overhead <span className="font-mono text-fg">{ms(totalMs)}</span>
        {upstreamMs != null && (
          <>
            {' '}
            · upstream <span className="font-mono text-fg">{ms(upstreamMs)}</span>
          </>
        )}
      </p>
    </div>
  )
}
