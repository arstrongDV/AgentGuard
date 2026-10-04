import { useNow } from '../lib/useNow'

const R = 22
const CIRCUMFERENCE = 2 * Math.PI * R

/** Time left until an approval is auto-resolved by the policy's on_timeout. */
export function CountdownRing({ createdAt, expiresAt }: { createdAt: string; expiresAt: string }) {
  const now = useNow(250)
  const total = Date.parse(expiresAt) - Date.parse(createdAt)
  const left = Math.max(0, Date.parse(expiresAt) - now)
  const fraction = total > 0 ? left / total : 0
  const urgent = left < 10_000
  return (
    <div className="relative size-14 shrink-0" title="Auto-resolved when the timer runs out (policy: approval.on_timeout)">
      <svg viewBox="0 0 56 56" className="size-14 -rotate-90">
        <circle cx="28" cy="28" r={R} fill="none" strokeWidth="4" className="stroke-line" />
        <circle
          cx="28"
          cy="28"
          r={R}
          fill="none"
          strokeWidth="4"
          strokeLinecap="round"
          className={urgent ? 'stroke-block' : 'stroke-approval'}
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={CIRCUMFERENCE * (1 - fraction)}
          style={{ transition: 'stroke-dashoffset 250ms linear' }}
        />
      </svg>
      <span className="tabular absolute inset-0 grid place-items-center font-mono text-sm font-semibold">{Math.ceil(left / 1000)}s</span>
    </div>
  )
}
