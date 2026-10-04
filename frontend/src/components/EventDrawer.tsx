import clsx from 'clsx'
import { useEffect, useState, type ReactNode } from 'react'
import { LuCheck, LuCopy, LuTriangleAlert, LuX } from 'react-icons/lu'
import { SEVERITY } from '../lib/decision'
import { dateTime, usd } from '../lib/format'
import { useEventDetail } from '../lib/queries'
import type { AuditEvent } from '../types/api'
import { DecisionBadge } from './DecisionBadge'
import { JsonView } from './JsonView'
import { PipelineTimeline } from './PipelineTimeline'
import { RedactionDiff } from './RedactionDiff'
import { RiskMeter } from './RiskMeter'

/** Everything about one decision: why (findings), what changed (diff), how fast (timeline). */
export function EventDrawer({ event, onClose }: { event: AuditEvent; onClose: () => void }) {
  const detail = useEventDetail(event.id)
  const full = detail.data ?? event

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const subject = event.tool ? `${event.tool.server}.${event.tool.name}` : (event.model ?? 'LLM')
  return (
    <aside
      aria-label="Event details"
      className="fixed inset-y-0 right-0 z-30 flex w-full flex-col border-l border-line bg-surface shadow-2xl shadow-black/50 lg:w-[44rem]"
    >
      <header className="flex items-start gap-3 border-b border-line p-4">
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <DecisionBadge decision={event.decision} monitorOnly={event.monitor_only} wouldHave={event.would_have} size="lg" />
            <span className="font-mono text-sm">{subject}</span>
            <span className="text-xs text-muted">
              {event.channel.toUpperCase()} {event.direction}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
            <span>
              agent <span className="text-fg">{event.agent_id}</span>
            </span>
            <span>{dateTime(event.ts)}</span>
            <RiskMeter value={event.risk} wide />
            <span>
              policy <span className="font-mono text-fg">{event.policy_version}</span>
            </span>
          </div>
        </div>
        <button onClick={onClose} className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-fg" aria-label="Close (Esc)">
          <LuX className="size-5" />
        </button>
      </header>

      <div className="flex-1 space-y-6 overflow-y-auto p-4">
        {event.error && (
          <div className="flex gap-2 rounded-md border border-line bg-surface-2 p-3 text-sm">
            <LuTriangleAlert className="mt-0.5 size-4 shrink-0 text-redact" />
            <span>
              <span className="font-medium">Upstream error</span> (not a security decision): {event.error}
            </span>
          </div>
        )}

        <Section title={`Why · ${event.findings.length} finding${event.findings.length === 1 ? '' : 's'}`}>
          {event.findings.length === 0 ? (
            <p className="text-sm text-muted">No rule fired. Every check that ran passed.</p>
          ) : (
            <ul className="divide-y divide-line rounded-md border border-line">
              {event.findings.map((f, i) => (
                <li key={i} className="flex items-start gap-3 p-2.5 text-sm">
                  <span className={clsx('mt-1.5 size-2 shrink-0 rounded-full', SEVERITY[f.severity].dot)} title={f.severity} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={clsx('font-mono text-xs', SEVERITY[f.severity].weight)}>{f.rule_id}</span>
                      <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-muted">{f.category}</span>
                      <span className="text-[11px] text-muted">{f.severity}</span>
                    </div>
                    <p className="mt-0.5 text-muted">{f.message}</p>
                  </div>
                  <span className="tabular font-mono text-xs text-muted" title="score">
                    {f.score.toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Content">
          {detail.isLoading ? (
            <p className="text-sm text-muted">Loading…</p>
          ) : full.original_text != null && full.redacted_text != null ? (
            <RedactionDiff original={full.original_text} redacted={full.redacted_text} />
          ) : (
            <p className="text-sm text-muted">{event.summary || 'No text content.'}</p>
          )}
        </Section>

        {event.tool?.arguments && Object.keys(event.tool.arguments).length > 0 && (
          <Section title="Tool arguments (as forwarded)">
            <JsonView value={event.tool.arguments} />
          </Section>
        )}

        <Section title="Pipeline">
          <PipelineTimeline timings={event.timings} totalMs={event.total_ms} upstreamMs={event.upstream_ms} />
        </Section>

        {(event.tokens || event.approval_id) && (
          <Section title="Details">
            <dl className="grid grid-cols-[8rem_1fr] gap-y-1 text-sm">
              {event.tokens && (
                <>
                  <dt className="text-muted">Tokens</dt>
                  <dd className="tabular font-mono">
                    {event.tokens.prompt} in · {event.tokens.completion} out
                  </dd>
                  <dt className="text-muted">Cost</dt>
                  <dd className="tabular font-mono">
                    {usd(event.cost_usd)} {event.cost_virtual && <span className="font-sans text-xs text-muted">(virtual)</span>}
                  </dd>
                </>
              )}
              {event.approval_id && (
                <>
                  <dt className="text-muted">Approval</dt>
                  <dd className="font-mono text-xs">{event.approval_id}</dd>
                </>
              )}
            </dl>
          </Section>
        )}

        <Section title="Trace">
          <div className="flex flex-wrap gap-2">
            <CopyChip label="trace" value={event.trace_id} />
            <CopyChip label="task" value={event.task_id} />
            <CopyChip label="event" value={event.id} />
          </div>
        </Section>

        <details className="group">
          <summary className="cursor-pointer text-xs text-muted select-none hover:text-fg">Raw event JSON</summary>
          <JsonView value={full} className="mt-2" />
        </details>
      </div>
    </aside>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">{title}</h3>
      {children}
    </section>
  )
}

function CopyChip({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard
      ?.writeText(value)
      .then(() => {
        setCopied(true)
        setTimeout(() => setCopied(false), 1200)
      })
      .catch(() => undefined)
  }
  return (
    <button
      onClick={copy}
      className="inline-flex items-center gap-1.5 rounded-md border border-line px-2 py-1 font-mono text-xs text-muted hover:text-fg"
      title={`Copy ${label} id`}
    >
      <span className="font-sans">{label}</span> {value.slice(-10)}
      {copied ? <LuCheck className="text-allow" /> : <LuCopy />}
    </button>
  )
}
