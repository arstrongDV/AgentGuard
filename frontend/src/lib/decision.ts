import type { IconType } from 'react-icons'
import { LuCircleCheck, LuHourglass, LuOctagonX, LuPenLine } from 'react-icons/lu'
import type { Decision, Severity } from '../types/api'

// Decision colors are global and semantic: allow green, redact amber, approval violet, block red.
// Class strings are written out in full so Tailwind can find them.
export const DECISION: Record<Decision, { label: string; icon: IconType; text: string; chip: string; dashed: string; hex: string }> = {
  allow: {
    label: 'Allow',
    icon: LuCircleCheck,
    text: 'text-allow',
    chip: 'bg-allow/15 text-allow border-allow/40',
    dashed: 'border-dashed border-allow/70 text-allow',
    hex: '#2fbf71',
  },
  redact: {
    label: 'Redact',
    icon: LuPenLine,
    text: 'text-redact',
    chip: 'bg-redact/15 text-redact border-redact/40',
    dashed: 'border-dashed border-redact/70 text-redact',
    hex: '#f0b429',
  },
  needs_approval: {
    label: 'Approval',
    icon: LuHourglass,
    text: 'text-approval',
    chip: 'bg-approval/15 text-approval border-approval/40',
    dashed: 'border-dashed border-approval/70 text-approval',
    hex: '#9b6dff',
  },
  block: {
    label: 'Block',
    icon: LuOctagonX,
    text: 'text-block',
    chip: 'bg-block/15 text-block border-block/40',
    dashed: 'border-dashed border-block/70 text-block',
    hex: '#f0544f',
  },
}

export const DECISIONS: Decision[] = ['allow', 'redact', 'needs_approval', 'block']

// Severity is shown by weight and a dot, never by decision colors.
export const SEVERITY: Record<Severity, { label: string; dot: string; weight: string }> = {
  low: { label: 'low', dot: 'bg-muted/50', weight: 'font-normal' },
  medium: { label: 'medium', dot: 'bg-muted', weight: 'font-medium' },
  high: { label: 'high', dot: 'bg-fg/80', weight: 'font-semibold' },
  critical: { label: 'critical', dot: 'bg-fg', weight: 'font-bold' },
}
