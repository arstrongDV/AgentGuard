import clsx from 'clsx'
import { useState } from 'react'
import { LuLayoutDashboard } from 'react-icons/lu'
import { Link } from 'react-router'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Cmd, EmptyState } from '../components/EmptyState'
import { Card, StatTile, WindowPicker } from '../components/ui'
import { DECISION } from '../lib/decision'
import { clockTime, ms } from '../lib/format'
import { useMetrics } from '../lib/queries'
import type { Metrics, MetricsWindow } from '../types/api'

// Decisions over time: "allow" is the neutral baseline, only the interventions carry a status color.
// (Validated: amber vs red stay distinct under color-vision deficiency; green vs amber do not.)
const SERIES = [
  { key: 'allow', label: 'Allow', color: '#3a4658' },
  { key: 'redact', label: 'Redact', color: DECISION.redact.hex },
  { key: 'block', label: 'Block', color: DECISION.block.hex },
] as const
const SURFACE = '#121821'
const TIER_NAME: Record<number, string> = { 0: 'T0 gates', 1: 'T1 rules', 2: 'T2 ML classifier', 3: 'T3 LLM judge' }

export function Overview() {
  const [range, setRange] = useState<MetricsWindow>('15m')
  const metrics = useMetrics(range)
  const m = metrics.data

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Overview</h1>
        <p className="text-sm text-muted">Security posture of all agent traffic through AgentGuard.</p>
        <div className="ml-auto">
          <WindowPicker value={range} onChange={setRange} options={['15m', '1h', '24h']} />
        </div>
      </div>

      {!m ? (
        <EmptyState icon={LuLayoutDashboard} title={metrics.isError ? 'Gateway offline' : 'Loading…'} />
      ) : m.totals.requests === 0 ? (
        <EmptyState icon={LuLayoutDashboard} title={`No traffic in the last ${range}`}>
          Run <Cmd>make demo</Cmd> or open the Attack Lab, then come back.
        </EmptyState>
      ) : (
        <>
          <Kpis m={m} />
          <div className="grid gap-4 xl:grid-cols-5">
            <Card title="Decisions over time" subtitle="Every pipeline run (requests and responses), per time bucket" className="xl:col-span-3">
              <DecisionsChart m={m} />
            </Card>
            <Card title="Top threat categories" subtitle="Events with at least one finding · click to inspect" className="xl:col-span-2">
              <Categories m={m} />
            </Card>
          </div>
          <Card
            title="Latency per check"
            subtitle="Cheap checks run on everything; the models only run when the cheap tiers ask for them. Log scale."
          >
            <LatencyLadder m={m} />
          </Card>
        </>
      )}
    </div>
  )
}

function Kpis({ m }: { m: Metrics }) {
  const t = m.totals
  const runs = t.allow + t.redact + t.block + t.needs_approval
  const pct = (n: number) => (runs ? `${((100 * n) / runs).toFixed(1)}%` : '–')
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
      <StatTile label="Requests" value={t.requests.toLocaleString()} hint={`${runs.toLocaleString()} pipeline runs`} />
      <StatTile label="Blocked" value={pct(t.block)} tone="block" hint={`${t.block.toLocaleString()} runs${t.monitor_only ? ` · ${t.monitor_only} monitor-only` : ''}`} />
      <StatTile label="Redacted" value={pct(t.redact)} tone="redact" hint={`${t.redact.toLocaleString()} runs`} />
      <StatTile label="Overhead p95" value={ms(m.overhead_ms.p95)} hint={`p50 ${ms(m.overhead_ms.p50)}`} />
      <StatTile
        label="Needed the ML model"
        value={`${m.tier_reach.t2_pct.toFixed(0)}%`}
        tone="accent"
        hint={`LLM judge ${m.tier_reach.t3_pct.toFixed(0)}% · rules decided the rest`}
      />
    </div>
  )
}

interface TooltipProps {
  active?: boolean
  label?: string
  payload?: { dataKey?: string; value?: number }[]
}

function DecisionsTooltip({ active, label, payload }: TooltipProps) {
  if (!active || !payload?.length || !label) return null
  const byKey = Object.fromEntries(payload.map((p) => [p.dataKey, p.value ?? 0]))
  return (
    <div className="rounded-md border border-line bg-surface-2 px-3 py-2 text-xs shadow-xl shadow-black/40">
      <p className="mb-1 text-muted">{clockTime(label)}</p>
      {[...SERIES].reverse().map((s) => (
        <p key={s.key} className="flex items-center gap-2">
          <span className="h-0.5 w-3 rounded" style={{ background: s.color }} />
          <span className="tabular font-mono font-semibold text-fg">{byKey[s.key] ?? 0}</span>
          <span className="text-muted">{s.label}</span>
        </p>
      ))}
    </div>
  )
}

function DecisionsChart({ m }: { m: Metrics }) {
  return (
    <div>
      <ul className="mb-2 flex gap-4 text-xs text-muted" aria-label="Legend">
        {SERIES.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm" style={{ background: s.color }} />
            {s.label}
          </li>
        ))}
      </ul>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={m.timeseries} margin={{ top: 4, right: 4, bottom: 0, left: -16 }} barCategoryGap={2}>
            <CartesianGrid vertical={false} stroke="#243041" strokeWidth={1} />
            <XAxis
              dataKey="ts"
              tickFormatter={(ts: string) => clockTime(ts).slice(0, 5)}
              tick={{ fill: '#8b98a9', fontSize: 11 }}
              axisLine={{ stroke: '#243041' }}
              tickLine={false}
              minTickGap={24}
            />
            <YAxis allowDecimals={false} tick={{ fill: '#8b98a9', fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip content={(p) => <DecisionsTooltip {...(p as unknown as TooltipProps)} />} cursor={{ fill: '#18202b' }} />
            {SERIES.map((s, i) => (
              <Bar
                key={s.key}
                dataKey={s.key}
                stackId="decisions"
                fill={s.color}
                stroke={SURFACE}
                strokeWidth={2}
                maxBarSize={24}
                radius={i === SERIES.length - 1 ? [4, 4, 0, 0] : 0}
                isAnimationActive={false}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <table className="sr-only">
        <caption>Decisions per time bucket</caption>
        <thead>
          <tr>
            <th>Time</th>
            {SERIES.map((s) => (
              <th key={s.key}>{s.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {m.timeseries.map((b) => (
            <tr key={b.ts}>
              <td>{clockTime(b.ts)}</td>
              <td>{b.allow}</td>
              <td>{b.redact}</td>
              <td>{b.block}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Categories({ m }: { m: Metrics }) {
  if (m.top_categories.length === 0) return <p className="text-sm text-muted">No findings in this window.</p>
  const max = Math.max(...m.top_categories.map((c) => c.count))
  return (
    <ul className="space-y-2.5">
      {m.top_categories.map((c) => (
        <li key={c.category}>
          <Link to={`/feed?category=${encodeURIComponent(c.category)}`} className="group block" title={`Show ${c.category} events in the Live Feed`}>
            <div className="mb-1 flex justify-between text-xs">
              <span className="font-mono group-hover:text-accent">{c.category}</span>
              <span className="tabular font-mono text-muted">{c.count}</span>
            </div>
            <div className="h-2 rounded-full bg-line">
              <div className="h-2 rounded-full bg-accent group-hover:bg-accent/80" style={{ width: `${(100 * c.count) / max}%` }} />
            </div>
          </Link>
        </li>
      ))}
    </ul>
  )
}

// log scale from 1 µs to 10 s, so 0.01 ms rules and 25 ms models fit on one axis
const LOG_MIN = -3
const LOG_MAX = 4
const logPct = (v: number) => (100 * (Math.log10(Math.max(v, 10 ** LOG_MIN)) - LOG_MIN)) / (LOG_MAX - LOG_MIN)

function LatencyLadder({ m }: { m: Metrics }) {
  const tiers = [...new Set(m.latency.map((r) => r.tier))].sort()
  const reach: Record<number, string> = {
    0: '100% of traffic',
    1: '100% of traffic',
    2: `${m.tier_reach.t2_pct.toFixed(1)}% of pipeline runs`,
    3: `${m.tier_reach.t3_pct.toFixed(1)}% of pipeline runs`,
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-4 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-4 rounded-full bg-accent" /> p50
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-0.5 bg-fg/70" /> p95
        </span>
        <span className="font-mono sm:ml-auto">log scale: 0.001 ms · 0.1 ms · 10 ms · 1 s</span>
      </div>
      {tiers.map((tier) => (
        <div key={tier}>
          <p className="mb-1.5 text-[11px] font-medium tracking-wide text-muted uppercase">
            {TIER_NAME[tier] ?? `T${tier}`} <span className="font-normal normal-case">· ran on {reach[tier]}</span>
          </p>
          <ul className="space-y-1.5">
            {m.latency
              .filter((r) => r.tier === tier)
              .map((r) => (
                <li
                  key={r.check}
                  // narrow screens: name + numbers on one line, the bar below; wide: name · bar · numbers
                  className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 text-xs sm:grid-cols-[9rem_1fr_9rem]"
                  title={`${r.runs} runs`}
                >
                  <span className="truncate font-mono">{r.check}</span>
                  <span className="relative col-span-2 row-start-2 h-2 rounded-full bg-line sm:col-span-1 sm:col-start-2 sm:row-start-1">
                    <span className={clsx('absolute inset-y-0 left-0 rounded-full bg-accent')} style={{ width: `${logPct(r.p50)}%` }} />
                    <span className="absolute -top-0.5 h-3 w-0.5 bg-fg/70" style={{ left: `${logPct(r.p95)}%` }} />
                  </span>
                  <span className="tabular col-start-2 row-start-1 text-right font-mono text-muted sm:col-start-3">
                    <span className="text-fg">{ms(r.p50)}</span> / {ms(r.p95)}
                  </span>
                </li>
              ))}
          </ul>
        </div>
      ))}
      {!tiers.includes(2) && (
        <p className="text-xs text-muted">The ML classifier has not run in this window: rules alone decided every request.</p>
      )}
    </div>
  )
}
