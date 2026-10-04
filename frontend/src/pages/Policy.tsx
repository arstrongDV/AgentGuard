import clsx from 'clsx'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { LuLoaderCircle, LuSlidersHorizontal } from 'react-icons/lu'
import { AdminToken } from '../components/AdminToken'
import { EmptyState } from '../components/EmptyState'
import { Card, Chip, Segmented } from '../components/ui'
import { ApiError } from '../lib/api'
import { usePatchPolicy, usePolicy } from '../lib/queries'
import type { EffectiveAgent, PolicyResponse, RawPolicy } from '../types/api'

type Strictness = 'low' | 'medium' | 'high'
type Mode = 'monitor' | 'enforce'

/**
 * Every switch here writes policy.yaml through PATCH /api/policy; the gateway reloads the file and the
 * YAML on the right shows exactly what changed. The file stays the single source of truth.
 */
export function Policy() {
  const policy = usePolicy()
  const patch = usePatchPolicy()
  const p = policy.data

  const error =
    patch.error instanceof ApiError
      ? patch.error.status === 401
        ? 'Admin token rejected: set the right one above.'
        : (patch.error.body as { error?: string })?.error ?? patch.error.message
      : patch.error?.message

  const apply = (body: Record<string, unknown>) => patch.mutate(body)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Policy</h1>
        <p className="text-sm text-muted">Changes are written to policy.yaml and hot-reloaded. No restart, no deploy.</p>
        {patch.isPending && <LuLoaderCircle className="animate-spin text-muted" aria-label="Saving" />}
        <AdminToken />
      </div>
      {error && <p className="rounded-md border border-block/50 bg-block/10 px-3 py-2 text-sm">Change rejected, policy unchanged: {error}</p>}

      {!p ? (
        <EmptyState icon={LuSlidersHorizontal} title={policy.isError ? 'Gateway offline' : 'Loading…'} />
      ) : (
        <div className="grid gap-4 xl:grid-cols-[1fr_28rem]">
          <div className="space-y-4">
            <GlobalSettings raw={p.raw} busy={patch.isPending} apply={apply} />
            {Object.entries(p.effective.agents).map(([id, agent]) => (
              <AgentSettings key={id} id={id} agent={agent} raw={p.raw} busy={patch.isPending} apply={apply} />
            ))}
          </div>
          <YamlView policy={p} />
        </div>
      )}
    </div>
  )
}

function GlobalSettings({ raw, busy, apply }: { raw: RawPolicy; busy: boolean; apply: (b: Record<string, unknown>) => void }) {
  const c = raw.controls
  return (
    <Card title="Global" subtitle="Applies to every agent that does not set its own value">
      <div className="divide-y divide-line">
        <Row label="Mode" help="Monitor logs what would be blocked but lets everything through: roll out safely, then enforce.">
          <Segmented<Mode>
            label="Mode"
            size="md"
            value={raw.mode}
            disabled={busy}
            onChange={(mode) => apply({ mode })}
            options={[
              { value: 'monitor', label: 'Monitor' },
              { value: 'enforce', label: 'Enforce' },
            ]}
          />
        </Row>
        <Row label="Strictness" help="Preset for thresholds, ML gating, loop limits and PII in answers.">
          <StrictnessPicker value={raw.strictness} disabled={busy} onChange={(strictness) => apply({ strictness })} />
        </Row>
        <Row label="Injection threshold" help="Classifier score at which a prompt or tool result is blocked.">
          <ThresholdSlider
            value={c.prompt_injection.threshold ?? 0.85}
            disabled={busy}
            onCommit={(threshold) => apply({ controls: { prompt_injection: { threshold } } })}
          />
        </Row>
        <Row label="LLM judge" help="Second opinion (Granite Guardian via Ollama) on uncertain and high-risk traffic.">
          <Segmented
            label="LLM judge"
            value={c.llm_judge.enabled ? 'on' : 'off'}
            disabled={busy}
            onChange={(v) => apply({ controls: { llm_judge: { enabled: v === 'on' } } })}
            options={[
              { value: 'off', label: 'Off' },
              { value: 'on', label: 'On' },
            ]}
          />
        </Row>
        <Row label="PII in prompts" help="What happens to emails, phones, IBANs and cards sent to the model.">
          <Segmented
            label="PII in prompts"
            value={c.pii.action}
            disabled={busy}
            onChange={(action) => apply({ controls: { pii: { action } } })}
            options={[
              { value: 'allow', label: 'Log only' },
              { value: 'redact', label: 'Redact' },
              { value: 'block', label: 'Block' },
            ]}
          />
        </Row>
        <Row label="Tool calls proposed by the model" help="A model asking to call a tool its agent may not use.">
          <Segmented
            label="Tool calls proposed by the model"
            value={c.output_tool_calls.action}
            disabled={busy}
            onChange={(action) => apply({ controls: { output_tool_calls: { action } } })}
            options={[
              { value: 'allow', label: 'Flag' },
              { value: 'block', label: 'Block' },
            ]}
          />
        </Row>
        <Row label="Blocked response" help="200 = a friendly assistant message (agents keep running), 403 = hard error.">
          <Segmented
            label="Blocked response"
            value={String(raw.block_status_code)}
            disabled={busy}
            onChange={(v) => apply({ block_status_code: Number(v) })}
            options={[
              { value: '200', label: '200 message' },
              { value: '403', label: '403 error' },
            ]}
          />
        </Row>
      </div>
    </Card>
  )
}

function AgentSettings({ id, agent, raw, busy, apply }: {
  id: string
  agent: EffectiveAgent
  raw: RawPolicy
  busy: boolean
  apply: (b: Record<string, unknown>) => void
}) {
  const own = raw.agents[id]
  const set = (field: 'strictness' | 'mode', value: string | null) => apply({ agents: { [id]: { [field]: value } } })
  return (
    <Card title={id} subtitle={own?.description}>
      <div className="divide-y divide-line">
        <Row label="Strictness" help={own?.strictness ? 'Set on this agent: overrides the global values.' : `Inherits the global setting (${raw.strictness}).`}>
          <Segmented
            label={`${id} strictness`}
            value={own?.strictness ?? 'inherit'}
            disabled={busy}
            onChange={(v) => set('strictness', v === 'inherit' ? null : v)}
            options={[
              { value: 'inherit', label: 'Inherit' },
              { value: 'low', label: 'Low' },
              { value: 'medium', label: 'Medium' },
              { value: 'high', label: 'High' },
            ]}
          />
        </Row>
        <Row label="Mode" help={own?.mode ? 'Set on this agent.' : `Inherits the global mode (${raw.mode}).`}>
          <Segmented
            label={`${id} mode`}
            value={own?.mode ?? 'inherit'}
            disabled={busy}
            onChange={(v) => set('mode', v === 'inherit' ? null : v)}
            options={[
              { value: 'inherit', label: 'Inherit' },
              { value: 'monitor', label: 'Monitor' },
              { value: 'enforce', label: 'Enforce' },
            ]}
          />
        </Row>
        <Row label="Effective" help="What the gateway actually applies to this agent right now.">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
            <Fact label="block at" value={agent.injection_threshold.toFixed(2)} />
            <Fact label="ML gate" value={agent.injection_gate.toFixed(2)} />
            <Fact label="loop limit" value={String(agent.loop_max_repeats)} />
            <Fact label="PII in answers" value={agent.pii_out_action} />
          </dl>
        </Row>
        <Row label="Tools">
          <div className="flex flex-wrap gap-1.5">
            {agent.tools_allowed.map((t) => (
              <Chip key={t}>{t}</Chip>
            ))}
            {agent.tools_need_approval.map((t) => (
              <Chip key={t} tone="approval" title="Needs human approval">
                {t} · approval
              </Chip>
            ))}
            {agent.tools_allowed.length + agent.tools_need_approval.length === 0 && <span className="text-xs text-muted">none</span>}
          </div>
        </Row>
        <Row label="Daily budget">
          <span className="font-mono text-xs">
            {agent.budget.tokens_per_day?.toLocaleString() ?? '∞'} tokens · ${agent.budget.usd_per_day ?? '∞'} ·{' '}
            {agent.budget.max_tool_calls_per_task ?? '∞'} tool calls per task
          </span>
        </Row>
      </div>
    </Card>
  )
}

function Row({ label, help, children }: { label: string; help?: string; children: ReactNode }) {
  return (
    <div className="grid gap-2 py-3 first:pt-0 last:pb-0 sm:grid-cols-[13rem_1fr] sm:items-center">
      <div>
        <p className="text-sm">{label}</p>
        {help && <p className="text-xs text-muted">{help}</p>}
      </div>
      <div>{children}</div>
    </div>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className="font-mono">{value}</dd>
    </div>
  )
}

function StrictnessPicker({ value, disabled, onChange }: { value: Strictness; disabled: boolean; onChange: (v: Strictness) => void }) {
  return (
    <Segmented<Strictness>
      label="Strictness"
      value={value}
      disabled={disabled}
      onChange={onChange}
      options={[
        { value: 'low', label: 'Low', title: 'threshold 0.95, ML only above risk 0.5, loop limit 8' },
        { value: 'medium', label: 'Medium', title: 'threshold 0.85, ML above risk 0.3, loop limit 5' },
        { value: 'high', label: 'High', title: 'threshold 0.70, ML on everything, loop limit 3, PII in answers blocked' },
      ]}
    />
  )
}

/** Applies on release, not on every pixel of drag: each change is a policy reload. */
function ThresholdSlider({ value, disabled, onCommit }: { value: number; disabled: boolean; onCommit: (v: number) => void }) {
  const [draft, setDraft] = useState<number | null>(null)
  const shown = draft ?? value
  const commit = () => {
    if (draft !== null && draft !== value) onCommit(draft)
    setDraft(null)
  }
  return (
    <div className="flex items-center gap-3">
      <input
        type="range"
        min={0.5}
        max={0.99}
        step={0.01}
        value={shown}
        disabled={disabled}
        onChange={(e) => setDraft(Number(e.target.value))}
        onPointerUp={commit}
        onKeyUp={commit}
        onBlur={commit}
        aria-label="Injection threshold"
        className="w-48 accent-[#4c8dff]"
      />
      <span className="tabular font-mono text-sm">{shown.toFixed(2)}</span>
    </div>
  )
}

/** Indexes of lines in `after` that are not part of the longest common subsequence with `before`. */
function changedLines(before: string[], after: string[]): Set<number> {
  const n = before.length
  const m = after.length
  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--) lcs[i][j] = before[i] === after[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1])
  const changed = new Set<number>()
  let i = 0
  let j = 0
  while (j < m) {
    if (i < n && before[i] === after[j]) {
      i++
      j++
    } else if (i < n && lcs[i + 1][j] >= lcs[i][j + 1]) i++
    else changed.add(j++)
  }
  return changed
}

/** The live file, with the lines that changed in the last reload highlighted. */
function YamlView({ policy }: { policy: PolicyResponse }) {
  const previous = useRef<{ version: string; lines: string[] } | null>(null)
  const container = useRef<HTMLPreElement>(null)
  const [changed, setChanged] = useState<Set<number>>(new Set())
  const lines = policy.yaml.split('\n')

  useEffect(() => {
    const prev = previous.current
    if (prev && prev.version !== policy.version) {
      const diff = changedLines(prev.lines, lines)
      setChanged(diff)
      // bring the first changed line into view inside the viewer (not the page)
      const first = Math.min(...diff)
      const row = container.current?.children[first] as HTMLElement | undefined
      if (container.current && row) container.current.scrollTop = row.offsetTop - container.current.clientHeight / 3
      const timer = setTimeout(() => setChanged(new Set()), 4000)
      previous.current = { version: policy.version, lines }
      return () => clearTimeout(timer)
    }
    previous.current = { version: policy.version, lines }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-run only when the version changes
  }, [policy.version])

  return (
    <Card
      title="policy.yaml"
      subtitle={
        <>
          version <span className="font-mono text-fg">{policy.version}</span> · edits in your editor show up here too
        </>
      }
      className="xl:sticky xl:top-16 xl:self-start"
    >
      <pre ref={container} className="relative max-h-[70vh] overflow-auto rounded-md border border-line bg-bg py-2 font-mono text-[11px] leading-5">
        {lines.map((line, i) => (
          <div key={i} className={clsx('flex px-2 transition-colors duration-700', changed.has(i) && 'bg-accent/20')}>
            <span className="mr-3 w-7 shrink-0 text-right text-muted/50 select-none">{i + 1}</span>
            <span className={clsx('whitespace-pre', line.trimStart().startsWith('#') && 'text-muted')}>{line || ' '}</span>
          </div>
        ))}
      </pre>
    </Card>
  )
}
