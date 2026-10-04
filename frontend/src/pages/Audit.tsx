import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { useState, type ReactNode } from 'react'
import { LuCheck, LuCopy, LuFileDown, LuSearch } from 'react-icons/lu'
import { Link } from 'react-router'
import { DecisionBadge } from '../components/DecisionBadge'
import { EmptyState } from '../components/EmptyState'
import { Card } from '../components/ui'
import { API_URL, api } from '../lib/api'
import { DECISION, DECISIONS } from '../lib/decision'
import { dateTime } from '../lib/format'
import { usePolicy } from '../lib/queries'
import type { EventPage } from '../types/api'

const CATEGORIES = ['prompt_injection', 'jailbreak', 'pii', 'secret', 'code_execution', 'deserialization', 'ssrf_exfil',
  'path_traversal', 'supply_chain', 'tool_acl', 'budget', 'banned_topic', 'harmful_content', 'auth']

interface Filters {
  from: string // datetime-local value, local time
  to: string
  agent: string
  decision: string
  channel: string
  category: string
}

const EMPTY: Filters = { from: '', to: '', agent: '', decision: '', channel: '', category: '' }

function toParams(f: Filters): URLSearchParams {
  const params = new URLSearchParams()
  if (f.from) params.set('from', new Date(f.from).toISOString())
  if (f.to) params.set('to', new Date(f.to).toISOString())
  for (const key of ['agent', 'decision', 'channel', 'category'] as const) if (f[key]) params.set(key, f[key])
  return params
}

/** Filter the audit log and take it away as CSV or JSONL (SIEM-friendly). */
export function Audit() {
  const [filters, setFilters] = useState<Filters>(EMPTY)
  const agents = Object.keys(usePolicy().data?.effective.agents ?? {})
  const params = toParams(filters)
  const preview = useQuery({
    queryKey: ['audit-preview', params.toString()],
    queryFn: () => api<EventPage>(`/api/events?limit=50&${params}`),
  })
  const exportUrl = (format: 'csv' | 'jsonl') => `${API_URL}/api/audit/export?${new URLSearchParams([...params, ['format', format]])}`
  const set = (key: keyof Filters) => (value: string) => setFilters((f) => ({ ...f, [key]: value }))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Audit export</h1>
        <p className="text-sm text-muted">Every decision AgentGuard made, with the rule that fired. Stored in SQLite and an append-only JSONL file.</p>
      </div>

      <Card title="Filters">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          <Field label="From">
            <input type="datetime-local" value={filters.from} onChange={(e) => set('from')(e.target.value)} className={inputClass} />
          </Field>
          <Field label="To">
            <input type="datetime-local" value={filters.to} onChange={(e) => set('to')(e.target.value)} className={inputClass} />
          </Field>
          <Field label="Agent">
            <Select value={filters.agent} onChange={set('agent')} options={[...agents, 'unknown'].map((a) => [a, a])} />
          </Field>
          <Field label="Decision">
            <Select value={filters.decision} onChange={set('decision')} options={DECISIONS.map((d) => [d, DECISION[d].label])} />
          </Field>
          <Field label="Channel">
            <Select value={filters.channel} onChange={set('channel')} options={[['llm', 'LLM'], ['mcp', 'MCP tools']]} />
          </Field>
          <Field label="Category">
            <Select value={filters.category} onChange={set('category')} options={CATEGORIES.map((c) => [c, c])} />
          </Field>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <a href={exportUrl('csv')} className={buttonClass('primary')}>
            <LuFileDown /> Download CSV
          </a>
          <a href={exportUrl('jsonl')} className={buttonClass('secondary')}>
            <LuFileDown /> Download JSONL
          </a>
          <CopyUrl url={exportUrl('jsonl')} />
          {Object.values(filters).some(Boolean) && (
            <button onClick={() => setFilters(EMPTY)} className="ml-auto text-xs text-muted hover:text-fg">
              Clear filters
            </button>
          )}
        </div>
      </Card>

      <Card title="Preview" subtitle="The 50 most recent matching events · the export contains all of them, oldest first">
        {!preview.data ? (
          <p className="text-sm text-muted">{preview.isError ? 'Gateway offline.' : 'Loading…'}</p>
        ) : preview.data.items.length === 0 ? (
          <EmptyState icon={LuSearch} title="No events match these filters" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[48rem] text-sm">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="py-2 pr-2 font-medium">Time</th>
                  <th className="px-2 py-2 font-medium">Agent</th>
                  <th className="px-2 py-2 font-medium">Event</th>
                  <th className="px-2 py-2 font-medium">Rules</th>
                  <th className="py-2 pl-2 font-medium">Decision</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {preview.data.items.map((e) => (
                  <tr key={e.id} className="hover:bg-surface-2/60">
                    <td className="tabular py-2 pr-2 font-mono text-xs whitespace-nowrap text-muted">
                      <Link to={`/feed?event=${e.id}`} className="hover:text-accent">
                        {dateTime(e.ts)}
                      </Link>
                    </td>
                    <td className="px-2 py-2">{e.agent_id}</td>
                    <td className="max-w-xs truncate px-2 py-2">
                      {e.tool ? <span className="font-mono text-xs text-accent">{`${e.tool.server}.${e.tool.name}`}</span> : e.summary}
                    </td>
                    <td className="max-w-xs truncate px-2 py-2 font-mono text-xs text-muted">
                      {[...new Set(e.findings.filter((f) => f.score > 0).map((f) => f.rule_id))].join(' ')}
                    </td>
                    <td className="py-2 pl-2">
                      <DecisionBadge decision={e.decision} monitorOnly={e.monitor_only} wouldHave={e.would_have} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}

const inputClass = 'w-full rounded-md border border-line bg-bg px-2 py-1.5 text-sm focus:border-accent focus:outline-none [color-scheme:dark]'

function buttonClass(kind: 'primary' | 'secondary') {
  return clsx(
    'inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium',
    kind === 'primary' ? 'bg-accent text-bg hover:bg-accent/90' : 'border border-line bg-surface-2 hover:border-fg/40',
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-muted">{label}</span>
      {children}
    </label>
  )
}

function Select({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className={inputClass}>
      <option value="">All</option>
      {options.map(([v, label]) => (
        <option key={v} value={v}>
          {label}
        </option>
      ))}
    </select>
  )
}

function CopyUrl({ url }: { url: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() =>
        navigator.clipboard
          ?.writeText(url)
          .then(() => {
            setCopied(true)
            setTimeout(() => setCopied(false), 1200)
          })
          .catch(() => undefined)
      }
      className="inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm text-muted hover:text-fg"
      title="For a SIEM or a cron job: the same export as a URL"
    >
      {copied ? <LuCheck className="text-allow" /> : <LuCopy />} Copy API URL
    </button>
  )
}
