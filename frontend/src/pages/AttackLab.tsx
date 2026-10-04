import clsx from 'clsx'
import { LuCircleAlert, LuCircleCheck, LuCircleDashed, LuLoaderCircle, LuPlay, LuSwords } from 'react-icons/lu'
import { Link } from 'react-router'
import { AdminToken } from '../components/AdminToken'
import { DecisionBadge } from '../components/DecisionBadge'
import { Cmd, EmptyState } from '../components/EmptyState'
import { Card, Chip } from '../components/ui'
import { ApiError } from '../lib/api'
import { DECISIONS } from '../lib/decision'
import { useDemoRuns, useRunScenario, useScenarios } from '../lib/queries'
import type { Decision, DemoRun, DemoScenario } from '../types/api'

/**
 * Run the demo attacks from the browser. The scenario runs the real demo agent through this gateway,
 * so every step also appears in the Live Feed, and approvals land on the Approvals page.
 */
export function AttackLab() {
  const scenarios = useScenarios()
  const runs = useDemoRuns()
  const run = useRunScenario()
  const latest = (name: string) => runs.data?.find((r) => r.scenario === name)

  const error =
    run.error instanceof ApiError && run.error.status === 401 ? 'Admin token rejected: set the right one above.' : run.error?.message

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Attack Lab</h1>
        <p className="text-sm text-muted">
          Each scenario replays what a compromised or confused agent would do. Needs the mock MCP servers (<Cmd>make mcp</Cmd>).
        </p>
        <AdminToken />
      </div>
      {error && <p className="rounded-md border border-block/50 bg-block/10 px-3 py-2 text-sm">{error}</p>}

      {!scenarios.data ? (
        <EmptyState icon={LuSwords} title={scenarios.isError ? 'Gateway offline' : 'Loading…'} />
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {scenarios.data.map((s) => (
            <ScenarioCard key={s.name} scenario={s} run={latest(s.name)} onRun={() => run.mutate(s.name)} starting={run.isPending && run.variables === s.name} />
          ))}
        </div>
      )}
    </div>
  )
}

function ScenarioCard({ scenario: s, run, onRun, starting }: { scenario: DemoScenario; run?: DemoRun; onRun: () => void; starting: boolean }) {
  const running = run?.status === 'running'
  const matches = run?.status === 'done' && run.steps.every((st) => st.decision === st.expect)
  return (
    <Card
      title={s.title}
      subtitle={
        <>
          <Chip>{s.agent}</Chip> <span className="ml-1 italic">“{s.prompt}”</span>
        </>
      }
      actions={
        <button
          onClick={onRun}
          disabled={running || starting}
          className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-bg hover:bg-accent/90 disabled:opacity-60"
        >
          {running || starting ? <LuLoaderCircle className="animate-spin" /> : <LuPlay />} {running ? 'Running' : 'Run'}
        </button>
      }
    >
      <ol className="space-y-2">
        {s.steps.map((step, i) => {
          const result = run?.steps[i]
          return (
            <li key={i} className="grid grid-cols-[1.25rem_1fr_auto] items-start gap-2 text-sm">
              <StepIcon status={result?.status} />
              <div className="min-w-0">
                <p className="text-xs text-muted">{step.note}</p>
                <p className="truncate font-mono text-xs" title={step.label}>
                  {step.kind === 'chat' ? `llm: ${step.label}` : step.label}
                </p>
                {result?.text && <p className="mt-0.5 line-clamp-2 text-xs text-muted">{result.text}</p>}
                {result?.status === 'running' && step.label.includes('transfer_money') && (
                  <Link to="/approvals" className="text-xs text-approval hover:underline">
                    Waiting for a human? Decide on the Approvals page →
                  </Link>
                )}
              </div>
              <div className="flex flex-col items-end gap-1">
                {result?.decision && isDecision(result.decision) ? (
                  <DecisionBadge decision={result.decision} />
                ) : (
                  <span className="text-[11px] text-muted">expect {step.expect}</span>
                )}
              </div>
            </li>
          )
        })}
      </ol>

      <footer className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-3 text-xs">
        <span className="text-muted">{s.stops_it}</span>
        {run && (
          <span className="ml-auto flex items-center gap-3">
            {run.status === 'error' && <span className="text-block">Run failed: {run.error}</span>}
            {run.status === 'done' && (
              <span className={matches ? 'text-allow' : 'text-redact'}>{matches ? 'All steps as expected' : 'Outcome differs from the script'}</span>
            )}
            <Link to={`/feed?task=${encodeURIComponent(run.task_id)}`} className="text-accent hover:underline">
              Open in Live Feed →
            </Link>
          </span>
        )}
      </footer>
    </Card>
  )
}

function StepIcon({ status }: { status?: string }) {
  const className = 'mt-0.5 size-4'
  if (status === 'done') return <LuCircleCheck className={clsx(className, 'text-muted')} aria-label="done" />
  if (status === 'running') return <LuLoaderCircle className={clsx(className, 'animate-spin text-accent')} aria-label="running" />
  if (status === 'pending') return <LuCircleDashed className={clsx(className, 'text-muted/60')} aria-label="pending" />
  return <LuCircleAlert className={clsx(className, 'text-transparent')} aria-hidden />
}

function isDecision(value: string): value is Decision {
  return (DECISIONS as string[]).includes(value)
}
