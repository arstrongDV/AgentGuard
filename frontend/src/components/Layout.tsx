import { useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { useEffect, type ReactNode } from 'react'
import type { IconType } from 'react-icons'
import {
  LuActivity,
  LuFileDown,
  LuGauge,
  LuLayoutDashboard,
  LuShieldCheck,
  LuSlidersHorizontal,
  LuUserCheck,
  LuWifiOff,
  LuX,
} from 'react-icons/lu'
import { NavLink, Outlet } from 'react-router'
import { API_URL } from '../lib/api'
import { useApprovals, useHealth, usePolicy } from '../lib/queries'
import { onSystemEvent, useEventStream } from '../lib/stream'
import { dismiss, toast, useToasts, type ToastKind } from '../lib/toast'
import { Cmd } from './EmptyState'

const NAV: { to: string; label: string; icon: IconType }[] = [
  { to: '/overview', label: 'Overview', icon: LuLayoutDashboard },
  { to: '/feed', label: 'Live Feed', icon: LuActivity },
  { to: '/approvals', label: 'Approvals', icon: LuUserCheck },
  { to: '/budgets', label: 'Budgets', icon: LuGauge },
  { to: '/policy', label: 'Policy', icon: LuSlidersHorizontal },
  { to: '/audit', label: 'Audit', icon: LuFileDown },
]

export function Layout() {
  const health = useHealth()
  return (
    <div className="flex min-h-svh">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <StatusBar />
        {health.isError && <OfflineBanner />}
        <main className="flex-1 px-4 py-5 md:px-6">
          <Outlet />
        </main>
      </div>
      <SystemEventBridge />
      <Toaster />
    </div>
  )
}

function Sidebar() {
  const pending = useApprovals('pending').data?.length ?? 0
  return (
    <nav className="sticky top-0 flex h-svh w-14 shrink-0 flex-col border-r border-line bg-surface md:w-52">
      <div className="flex items-center gap-2 px-3 py-4 md:px-4">
        <LuShieldCheck className="size-7 text-accent" aria-hidden />
        <span className="hidden text-lg font-semibold tracking-tight md:inline">AgentGuard</span>
      </div>
      <ul className="flex flex-col gap-0.5 px-2">
        {NAV.map(({ to, label, icon: Icon }) => (
          <li key={to}>
            <NavLink
              to={to}
              title={label}
              className={({ isActive }) =>
                clsx(
                  'relative flex items-center gap-3 rounded-md px-2.5 py-2 text-sm transition-colors',
                  isActive ? 'bg-surface-2 text-fg' : 'text-muted hover:bg-surface-2/60 hover:text-fg',
                )
              }
            >
              <Icon className="size-[18px]" aria-hidden />
              <span className="hidden flex-1 md:inline">{label}</span>
              {to === '/approvals' && pending > 0 && (
                <span className="tabular absolute top-0.5 right-0.5 rounded-full bg-approval px-1.5 text-[10px] font-semibold text-bg md:static md:text-xs">
                  {pending}
                </span>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}

function StatusBar() {
  const health = useHealth()
  const policy = usePolicy()
  const { status } = useEventStream()
  const h = health.data
  const mode = policy.data?.effective.mode
  return (
    <header className="sticky top-0 z-20 flex flex-wrap items-center gap-2 border-b border-line bg-bg/90 px-4 py-2.5 backdrop-blur md:px-6">
      <Pill ok={!health.isError && !!h} label="Gateway" value={health.isError ? 'offline' : h ? 'online' : '…'} />
      <Pill ok={h?.llm !== 'offline'} label="LLM" value={h?.llm ?? '…'} />
      <span title={h?.ml_detail || 'T2 prompt-injection classifier'}>
        <Pill ok={h?.ml === 'loaded'} neutral={h?.ml !== 'loaded'} label="ML" value={h ? (h.ml === 'loaded' || h.ml === 'loading' ? h.ml : 'rules only') : '…'} />
      </span>
      <span title="T3 LLM judge (Granite Guardian via Ollama), asked only about uncertain or high-risk traffic">
        <Pill ok={h?.judge === 'available'} neutral={h?.judge !== 'available'} label="Judge" value={h?.judge === 'available' ? 'on' : 'off'} />
      </span>
      <span className="hidden sm:contents">
        <Pill ok label="Signatures" value={h ? String(h.signatures) : '…'} />
        <Pill ok label="Policy" value={h?.policy_version ?? '…'} mono />
      </span>
      <div className="ml-auto flex items-center gap-3">
        {mode && (
          <NavLink
            to="/policy"
            title="Change on the Policy page"
            className={clsx(
              'rounded-md border px-2.5 py-1 text-xs font-semibold tracking-wider',
              mode === 'enforce' ? 'border-block/50 bg-block/15 text-block' : 'border-dashed border-redact/70 text-redact',
            )}
          >
            {mode.toUpperCase()}
          </NavLink>
        )}
        <span className="flex items-center gap-1.5 text-xs text-muted" title="Live event stream">
          <span
            className={clsx(
              'size-2 rounded-full',
              status === 'live' ? 'animate-pulse-dot bg-allow' : status === 'connecting' ? 'bg-redact' : 'bg-block',
            )}
          />
          {status}
        </span>
      </div>
    </header>
  )
}

function Pill({ ok, neutral, label, value, mono }: { ok: boolean; neutral?: boolean; label: string; value: string; mono?: boolean }) {
  return (
    <span className="flex items-center gap-1.5 rounded-md border border-line px-2 py-1 text-xs">
      <span className={clsx('size-1.5 rounded-full', neutral ? 'bg-muted' : ok ? 'bg-allow' : 'bg-block')} />
      <span className="text-muted">{label}</span>
      <span className={clsx('text-fg', mono && 'font-mono')}>{value}</span>
    </span>
  )
}

function OfflineBanner() {
  return (
    <div className="flex items-center gap-2 border-b border-block/40 bg-block/10 px-4 py-2 text-sm md:px-6">
      <LuWifiOff className="shrink-0 text-block" aria-hidden />
      <span>
        Gateway offline at <span className="font-mono">{API_URL}</span>. Showing the last known data. Start it with <Cmd>make gateway</Cmd>.
      </span>
    </div>
  )
}

/** Turns live system events into toasts and fresh data. */
function SystemEventBridge() {
  const client = useQueryClient()
  useEffect(
    () =>
      onSystemEvent((event) => {
        switch (event.type) {
          case 'policy_reloaded':
            void client.invalidateQueries({ queryKey: ['policy'] })
            void client.invalidateQueries({ queryKey: ['health'] })
            toast({ kind: 'info', title: `Policy reloaded ${event.old_version} → ${event.new_version}`, body: event.summary })
            break
          case 'policy_error':
            toast({ kind: 'error', title: 'Policy change rejected, previous version kept', body: event.message })
            break
          case 'approval_requested':
            void client.invalidateQueries({ queryKey: ['approvals'] })
            toast({
              kind: 'approval',
              title: `${event.approval.agent_id} wants to call ${event.approval.tool.name}`,
              body: 'Waiting for a human decision.',
              href: '/approvals',
            })
            break
          case 'approval_resolved':
            void client.invalidateQueries({ queryKey: ['approvals'] })
            break
          case 'feed_updated':
            void client.invalidateQueries({ queryKey: ['health'] })
            toast({ kind: 'info', title: `Signature feed updated (${event.count} signatures)`, body: `version ${event.feed_version}` })
            break
        }
      }),
    [client],
  )
  return null
}

const TOAST_STYLE: Record<ToastKind, string> = {
  info: 'border-accent/50',
  success: 'border-allow/50',
  error: 'border-block/60',
  approval: 'border-approval/60',
}

function Toaster() {
  const toasts = useToasts()
  return (
    <div className="pointer-events-none fixed right-4 bottom-4 z-40 flex w-80 flex-col gap-2" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={clsx('pointer-events-auto rounded-lg border bg-surface-2 p-3 shadow-xl shadow-black/40', TOAST_STYLE[t.kind])}>
          <div className="flex items-start gap-2">
            <div className="min-w-0 flex-1">
              <ToastTitle href={t.href}>{t.title}</ToastTitle>
              {t.body && <p className="mt-0.5 line-clamp-3 text-xs text-muted">{t.body}</p>}
            </div>
            <button onClick={() => dismiss(t.id)} className="text-muted hover:text-fg" aria-label="Dismiss">
              <LuX />
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}

function ToastTitle({ href, children }: { href?: string; children: ReactNode }) {
  const className = 'text-sm font-medium'
  return href ? (
    <NavLink to={href} className={clsx(className, 'hover:underline')}>
      {children}
    </NavLink>
  ) : (
    <p className={className}>{children}</p>
  )
}
