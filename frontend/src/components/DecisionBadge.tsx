import clsx from 'clsx'
import { DECISION } from '../lib/decision'
import type { Decision } from '../types/api'

interface Props {
  decision: Decision
  monitorOnly?: boolean
  wouldHave?: Decision | null
  size?: 'sm' | 'lg'
}

/** Filled pill for enforced decisions; dashed outline + "would block" for monitor mode. */
export function DecisionBadge({ decision, monitorOnly = false, wouldHave, size = 'sm' }: Props) {
  if (monitorOnly && wouldHave) {
    const style = DECISION[wouldHave]
    const Icon = style.icon
    return (
      <span
        title={`Monitor mode: AgentGuard would have applied "${style.label}" but only logged it`}
        className={clsx('inline-flex items-center gap-1 rounded-full border whitespace-nowrap', style.dashed, sizes[size])}
      >
        <Icon aria-hidden /> would {style.label.toLowerCase()}
      </span>
    )
  }
  const style = DECISION[decision]
  const Icon = style.icon
  return (
    <span className={clsx('inline-flex items-center gap-1 rounded-full border font-medium whitespace-nowrap', style.chip, sizes[size])}>
      <Icon aria-hidden /> {style.label}
    </span>
  )
}

const sizes = {
  sm: 'px-2 py-0.5 text-xs',
  lg: 'px-3 py-1 text-sm',
}
