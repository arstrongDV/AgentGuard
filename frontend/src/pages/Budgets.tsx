import { LuGauge } from 'react-icons/lu'
import { Link } from 'react-router'
import { EmptyState } from '../components/EmptyState'
import { Card, Chip, Meter } from '../components/ui'
import { usd } from '../lib/format'
import { useBudgets } from '../lib/queries'
import type { BudgetStatus } from '../types/api'

export function Budgets() {
  const budgets = useBudgets()
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Budgets</h1>
        <p className="text-sm text-muted">Daily spend per agent against the limits in policy.yaml. Budgets reset at 00:00 UTC.</p>
      </div>
      {!budgets.data ? (
        <EmptyState icon={LuGauge} title={budgets.isError ? 'Gateway offline' : 'Loading…'} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {budgets.data.map((b) => (
            <AgentBudget key={b.agent_id} b={b} />
          ))}
        </div>
      )}
    </div>
  )
}

function AgentBudget({ b }: { b: BudgetStatus }) {
  const hours = Math.floor(b.resets_in_s / 3600)
  const minutes = Math.floor((b.resets_in_s % 3600) / 60)
  return (
    <Card
      title={b.agent_id}
      subtitle={`resets in ${hours}h ${minutes.toString().padStart(2, '0')}m`}
      actions={
        b.usd.virtual && (
          <Chip title="Local model: priced with a virtual cost table to show what the same traffic would cost on a cloud API">
            virtual cost
          </Chip>
        )
      }
    >
      <div className="space-y-4">
        <Meter label="Tokens today" value={b.tokens.used} limit={b.tokens.limit} format={(n) => n.toLocaleString()} />
        <Meter label="Cost today" value={b.usd.used} limit={b.usd.limit} format={usd} />
        <Meter label="Requests in the last minute" value={b.rate.rpm} limit={b.rate.limit} format={(n) => n.toLocaleString()} />

        <div>
          <p className="mb-1.5 text-xs text-muted">By model</p>
          {b.by_model.length === 0 ? (
            <p className="text-sm text-muted">No LLM traffic today.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="py-1 font-medium">Model</th>
                  <th className="py-1 text-right font-medium">Tokens</th>
                  <th className="py-1 text-right font-medium">Cost</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {b.by_model.map((m) => (
                  <tr key={m.model}>
                    <td className="py-1.5 font-mono text-xs">{m.model}</td>
                    <td className="tabular py-1.5 text-right font-mono text-xs">{m.tokens.toLocaleString()}</td>
                    <td className="tabular py-1.5 text-right font-mono text-xs">{usd(m.usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-line pt-3 text-sm">
          <span className="text-muted">Blocked today</span>
          <Link to={`/feed?agent=${encodeURIComponent(b.agent_id)}&decision=block`} className="font-medium hover:text-accent">
            {b.blocked_today.toLocaleString()} events →
          </Link>
        </div>
      </div>
    </Card>
  )
}
