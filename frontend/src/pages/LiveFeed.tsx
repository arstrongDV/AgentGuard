import clsx from 'clsx'
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { LuActivity, LuArrowRight, LuPause, LuPlay, LuSearch } from 'react-icons/lu'
import { useSearchParams } from 'react-router'
import { DecisionBadge } from '../components/DecisionBadge'
import { Cmd, EmptyState } from '../components/EmptyState'
import { EventDrawer } from '../components/EventDrawer'
import { RiskMeter } from '../components/RiskMeter'
import { DECISION, DECISIONS } from '../lib/decision'
import { clockTime, ms } from '../lib/format'
import { useEventStream } from '../lib/stream'
import type { AuditEvent } from '../types/api'

export function LiveFeed() {
  const { events: liveEvents, status } = useEventStream()
  const [params, setParams] = useSearchParams()
  const [paused, setPaused] = useState<AuditEvent[] | null>(null)
  const search = useRef<HTMLInputElement>(null)
  const [mountedAt] = useState(() => Date.now()) // rows newer than this flash in

  const agent = params.get('agent') ?? ''
  const decision = params.get('decision') ?? ''
  const channel = params.get('channel') ?? ''
  const category = params.get('category') ?? ''
  const task = params.get('task') ?? ''
  const query = params.get('q') ?? ''
  const selectedId = params.get('event') // in the URL, so an event can be linked to and survives reloads
  const setFilter = (key: string, value: string) =>
    setParams((p) => {
      if (value) p.set(key, value)
      else p.delete(key)
      return p
    })

  const events = paused ?? liveEvents
  const newWhilePaused = paused ? liveEvents.filter((e) => e.id > (paused[0]?.id ?? '')).length : 0
  const agents = useMemo(() => [...new Set(liveEvents.map((e) => e.agent_id))].sort(), [liveEvents])

  const visible = useMemo(() => {
    const q = query.toLowerCase()
    return events.filter(
      (e) =>
        (!agent || e.agent_id === agent) &&
        (!decision || (decision === 'monitor' ? e.monitor_only : e.decision === decision)) &&
        (!channel || e.channel === channel) &&
        (!category || e.findings.some((f) => f.category === category)) &&
        (!task || e.task_id === task) &&
        (!q ||
          e.summary.toLowerCase().includes(q) ||
          e.agent_id.includes(q) ||
          e.tool?.name.includes(q) ||
          e.findings.some((f) => f.rule_id.toLowerCase().includes(q) || f.category.includes(q))),
    )
  }, [events, agent, decision, channel, category, task, query])

  const selected = useMemo(() => events.find((e) => e.id === selectedId) ?? liveEvents.find((e) => e.id === selectedId) ?? null, [
    events,
    liveEvents,
    selectedId,
  ])

  // "/" focuses search (when not already typing somewhere)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement
      if (e.key === '/' && !typing) {
        e.preventDefault()
        search.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const setSelectedId = useCallback(
    (id: string | null) =>
      setParams((p) => {
        if (id) p.set('event', id)
        else p.delete('event')
        return p
      }),
    [setParams],
  )
  const close = useCallback(() => setSelectedId(null), [setSelectedId])
  const filtered = agent || decision || channel || category || task || query

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-2 text-xl font-semibold">Live Feed</h1>
        <Select label="Agent" value={agent} onChange={(v) => setFilter('agent', v)} options={agents.map((a) => [a, a])} />
        <Select
          label="Decision"
          value={decision}
          onChange={(v) => setFilter('decision', v)}
          options={[...DECISIONS.map((d) => [d, DECISION[d].label] as [string, string]), ['monitor', 'Monitor only']]}
        />
        <Select label="Channel" value={channel} onChange={(v) => setFilter('channel', v)} options={[['llm', 'LLM'], ['mcp', 'MCP tools']]} />
        {category && (
          <button onClick={() => setFilter('category', '')} className="rounded-md border border-line px-2 py-1.5 text-xs text-muted hover:text-fg">
            category: <span className="text-fg">{category}</span> ×
          </button>
        )}
        {task && (
          <button onClick={() => setFilter('task', '')} className="rounded-md border border-line px-2 py-1.5 text-xs text-muted hover:text-fg">
            task: <span className="font-mono text-fg">{task}</span> ×
          </button>
        )}
        <label className="relative">
          <LuSearch className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted" aria-hidden />
          <input
            ref={search}
            value={query}
            onChange={(e) => setFilter('q', e.target.value)}
            placeholder="Search rule, tool, text…  ( / )"
            className="w-64 rounded-md border border-line bg-surface py-1.5 pr-2 pl-8 text-sm placeholder:text-muted/70 focus:border-accent focus:outline-none"
          />
        </label>
        <div className="ml-auto flex items-center gap-2">
          {paused && newWhilePaused > 0 && (
            <button onClick={() => setPaused(null)} className="rounded-full bg-accent px-3 py-1 text-xs font-medium text-bg">
              {newWhilePaused} new · resume
            </button>
          )}
          <button
            onClick={() => setPaused(paused ? null : liveEvents)}
            className={clsx(
              'flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm',
              paused ? 'border-redact/60 text-redact' : 'border-line text-muted hover:text-fg',
            )}
            title="Freeze the feed while you explain an event"
          >
            {paused ? <LuPlay /> : <LuPause />} {paused ? 'Paused' : 'Pause'}
          </button>
        </div>
      </div>

      {visible.length === 0 ? (
        filtered ? (
          <EmptyState icon={LuSearch} title="No events match these filters" />
        ) : (
          <EmptyState icon={LuActivity} title={status === 'offline' ? 'Waiting for the gateway…' : 'No traffic yet'}>
            Start the stack with <Cmd>make gateway</Cmd> and <Cmd>make mcp</Cmd>, then run <Cmd>make demo</Cmd>. Every prompt, completion,
            tool call and tool result shows up here as it happens.
          </EmptyState>
        )
      ) : (
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full min-w-[60rem] table-fixed text-sm">
            <colgroup>
              <col className="w-28" />
              <col className="w-32" />
              <col className="w-24" />
              <col />
              <col className="w-36" />
              <col className="w-28" />
              <col className="w-24" />
            </colgroup>
            <thead className="bg-surface text-left text-xs text-muted">
              <tr>
                <th className="py-2 pr-2 pl-4 font-medium">Time</th>
                <th className="px-2 py-2 font-medium">Agent</th>
                <th className="px-2 py-2 font-medium">Channel</th>
                <th className="px-2 py-2 font-medium">Summary</th>
                <th className="px-2 py-2 font-medium">Decision</th>
                <th className="px-2 py-2 font-medium">Risk</th>
                <th className="py-2 pr-4 pl-2 text-right font-medium">Overhead</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {visible.map((e, i) => (
                <Row
                  key={e.id}
                  event={e}
                  isNew={Date.parse(e.ts) > mountedAt}
                  sameTraceAsNeighbour={visible[i - 1]?.trace_id === e.trace_id || visible[i + 1]?.trace_id === e.trace_id}
                  selected={e.id === selectedId}
                  onSelect={() => setSelectedId(e.id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-muted">
        Showing {visible.length} of {events.length} recent events · click a row for details · Esc closes
      </p>

      {selected && <EventDrawer event={selected} onClose={close} />}
    </div>
  )
}

function Row({
  event: e,
  isNew,
  sameTraceAsNeighbour,
  selected,
  onSelect,
}: {
  event: AuditEvent
  isNew: boolean
  sameTraceAsNeighbour: boolean
  selected: boolean
  onSelect: () => void
}) {
  const topFinding = e.findings.find((f) => f.score > 0)
  return (
    <tr
      onClick={onSelect}
      className={clsx('cursor-pointer hover:bg-surface-2/70', selected && 'bg-surface-2', isNew && 'animate-flash')}
      style={{ '--flash': DECISION[e.decision].hex } as CSSProperties}
    >
      <td className={clsx('tabular py-2 pr-2 pl-4 font-mono text-xs whitespace-nowrap text-muted', sameTraceAsNeighbour && 'border-l-2 border-accent/50')}>
        {clockTime(e.ts)}
      </td>
      <td className="truncate px-2 py-2 whitespace-nowrap">{e.agent_id}</td>
      <td className="px-2 py-2 text-xs whitespace-nowrap text-muted">
        <span className="inline-flex items-center gap-1">
          {e.channel === 'llm' ? 'LLM' : 'MCP'}
          <LuArrowRight className={clsx('size-3', e.direction === 'response' && 'rotate-180')} aria-label={e.direction} />
        </span>
      </td>
      <td className="px-2 py-2">
        <div className="truncate">
          {e.tool && <span className="mr-2 font-mono text-xs text-accent">{`${e.tool.server}.${e.tool.name}`}</span>}
          <span className={e.tool ? 'text-muted' : ''}>{e.tool && e.summary.startsWith(`${e.tool.server}.`) ? '' : e.summary}</span>
        </div>
        {topFinding && e.decision !== 'allow' && (
          <div className="truncate font-mono text-[11px] text-muted">
            {topFinding.rule_id} · {topFinding.message}
          </div>
        )}
        {e.error && <div className="truncate text-[11px] text-redact">error: {e.error}</div>}
      </td>
      <td className="px-2 py-2">
        <DecisionBadge decision={e.decision} monitorOnly={e.monitor_only} wouldHave={e.would_have} />
      </td>
      <td className="px-2 py-2">
        <RiskMeter value={e.risk} />
      </td>
      <td className="tabular py-2 pr-4 pl-2 text-right font-mono text-xs text-muted">{ms(e.total_ms)}</td>
    </tr>
  )
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  options: [string, string][]
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={clsx(
        'rounded-md border bg-surface px-2 py-1.5 text-sm focus:border-accent focus:outline-none',
        value ? 'border-accent/60 text-fg' : 'border-line text-muted',
      )}
    >
      <option value="">{label}: all</option>
      {options.map(([v, text]) => (
        <option key={v} value={v}>
          {text}
        </option>
      ))}
    </select>
  )
}
