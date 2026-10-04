import type { ReactNode } from 'react'
import type { IconType } from 'react-icons'

export function EmptyState({ icon: Icon, title, children }: { icon: IconType; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-line px-6 py-16 text-center">
      <Icon className="size-8 text-muted" aria-hidden />
      <p className="text-base font-medium">{title}</p>
      {children && <div className="max-w-md text-sm text-muted">{children}</div>}
    </div>
  )
}

/** Inline code for commands in hints, e.g. <Cmd>make demo</Cmd>. */
export function Cmd({ children }: { children: ReactNode }) {
  return <code className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-xs text-fg">{children}</code>
}
