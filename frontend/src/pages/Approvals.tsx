import clsx from 'clsx'
import { useState } from 'react'
import { LuCheck, LuUserCheck, LuX } from 'react-icons/lu'
import { AdminToken } from '../components/AdminToken'
import { CountdownRing } from '../components/CountdownRing'
import { Cmd, EmptyState } from '../components/EmptyState'
import { JsonView } from '../components/JsonView'
import { RiskMeter } from '../components/RiskMeter'
import { ApiError } from '../lib/api'
import { clockTime, relative } from '../lib/format'
import { useApprovals, useHealth, useResolveApproval } from '../lib/queries'
import { useNow } from '../lib/useNow'
import type { Approval, ApprovalStatus } from '../types/api'

export function Approvals() {
  const pending = useApprovals('pending')
  const all = useApprovals()
  const history = (all.data ?? []).filter((a) => a.status !== 'pending')

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Approvals</h1>
        <p className="text-sm text-muted">Tool calls listed in a policy's tools_need_approval wait here for a human decision.</p>
        <AdminToken />
      </div>

      {pending.data && pending.data.length > 0 ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {pending.data.map((a) => (
            <PendingCard key={a.id} approval={a} />
          ))}
        </div>
      ) : (
        <EmptyState icon={LuUserCheck} title={pending.isLoading ? 'Loading…' : 'Nothing is waiting for approval'}>
          Run <Cmd>make demo-live</Cmd>: finance-bot tries a 900 EUR transfer and the call is held here until you decide.
        </EmptyState>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold text-muted">History</h2>
        {history.length === 0 ? (
          <p className="text-sm text-muted">No decisions yet.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full min-w-[40rem] text-sm">
              <thead className="bg-surface text-left text-xs text-muted">
                <tr>
                  <th className="py-2 pr-2 pl-4 font-medium">Requested</th>
                  <th className="px-2 py-2 font-medium">Agent</th>
                  <th className="px-2 py-2 font-medium">Tool</th>
                  <th className="px-2 py-2 font-medium">Arguments</th>
                  <th className="px-2 py-2 font-medium">Outcome</th>
                  <th className="py-2 pr-4 pl-2 font-medium">Note</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {history.map((a) => (
                  <tr key={a.id}>
                    <td className="tabular py-2 pr-2 pl-4 font-mono text-xs text-muted">{clockTime(a.created_at)}</td>
                    <td className="px-2 py-2">{a.agent_id}</td>
                    <td className="px-2 py-2 font-mono text-xs">{`${a.tool.server}.${a.tool.name}`}</td>
                    <td className="max-w-xs truncate px-2 py-2 font-mono text-xs text-muted">{JSON.stringify(a.tool.arguments)}</td>
                    <td className="px-2 py-2">
                      <Outcome status={a.status} />
                    </td>
                    <td className="py-2 pr-4 pl-2 text-xs text-muted">{a.note ?? ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

function PendingCard({ approval: a }: { approval: Approval }) {
  const resolve = useResolveApproval()
  const offline = useHealth().isError
  const [note, setNote] = useState('')
  const now = useNow(5000)
  const error = resolve.error instanceof ApiError && resolve.error.status === 401 ? 'Admin token rejected: set the right one above.' : resolve.error?.message

  const decide = (decision: 'approve' | 'deny') => resolve.mutate({ id: a.id, decision, note })

  return (
    <article className="flex flex-col gap-4 rounded-lg border border-approval/50 bg-surface p-4">
      <header className="flex items-start gap-4">
        <CountdownRing createdAt={a.created_at} expiresAt={a.expires_at} />
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted">
            {a.agent_id} · requested {relative(a.created_at, now)}
          </p>
          <p className="truncate font-mono text-lg">{`${a.tool.server}.${a.tool.name}`}</p>
          <RiskMeter value={a.risk} wide />
        </div>
      </header>

      <JsonView value={a.tool.arguments ?? {}} />

      {a.findings.length > 0 && (
        <ul className="space-y-1 text-xs">
          {a.findings.map((f, i) => (
            <li key={i} className="flex gap-2">
              <span className="font-mono">{f.rule_id}</span>
              <span className="text-muted">{f.message}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Note for the audit log (optional)"
          className="min-w-40 flex-1 rounded-md border border-line bg-bg px-3 py-2 text-sm placeholder:text-muted/70 focus:border-accent focus:outline-none"
        />
        <button
          onClick={() => decide('approve')}
          disabled={resolve.isPending || offline}
          className="flex items-center gap-1.5 rounded-md border border-line bg-surface-2 px-4 py-2 text-sm font-medium hover:border-fg/40 disabled:opacity-50"
        >
          <LuCheck /> Approve
        </button>
        <button
          onClick={() => decide('deny')}
          disabled={resolve.isPending || offline}
          className="flex items-center gap-1.5 rounded-md bg-block px-4 py-2 text-sm font-semibold text-bg hover:bg-block/90 disabled:opacity-50"
        >
          <LuX /> Deny
        </button>
      </div>
      {error && <p className="text-sm text-block">{error}</p>}
      {offline && <p className="text-xs text-muted">Gateway offline: decisions are disabled until it is back.</p>}
    </article>
  )
}

const OUTCOME: Record<ApprovalStatus, { label: string; className: string }> = {
  pending: { label: 'pending', className: 'text-approval' },
  approved: { label: 'approved', className: 'text-allow' },
  denied: { label: 'denied', className: 'text-block' },
  timeout: { label: 'timed out', className: 'text-muted' },
}

function Outcome({ status }: { status: ApprovalStatus }) {
  return <span className={clsx('text-sm font-medium', OUTCOME[status].className)}>{OUTCOME[status].label}</span>
}
