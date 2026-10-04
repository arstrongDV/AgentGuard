import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type {
  Approval,
  ApprovalStatus,
  AuditEvent,
  BudgetStatus,
  DemoRun,
  DemoScenario,
  Health,
  Metrics,
  MetricsWindow,
  PolicyResponse,
} from '../types/api'
import { adminHeaders, api } from './api'

export function useHealth() {
  return useQuery({ queryKey: ['health'], queryFn: () => api<Health>('/health'), refetchInterval: 5_000, retry: false })
}

export function usePolicy() {
  return useQuery({ queryKey: ['policy'], queryFn: () => api<PolicyResponse>('/api/policy') })
}

export function useApprovals(status?: ApprovalStatus) {
  return useQuery({
    queryKey: ['approvals', status ?? 'all'],
    queryFn: () => api<Approval[]>(`/api/approvals${status ? `?status=${status}` : ''}`),
    refetchInterval: 5_000, // SSE invalidates instantly; this is the fallback
  })
}

/** Full event, including original and redacted text (the list and the stream omit them). */
export function useEventDetail(id: string | null) {
  return useQuery({
    queryKey: ['event', id],
    queryFn: () => api<AuditEvent>(`/api/events/${id}`),
    enabled: id !== null,
    staleTime: Infinity, // audit events never change
  })
}

export function useResolveApproval() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, decision, note }: { id: string; decision: 'approve' | 'deny'; note?: string }) =>
      api<Approval>(`/api/approvals/${id}`, {
        method: 'POST',
        headers: adminHeaders(),
        body: JSON.stringify({ decision, note: note || null }),
      }),
    onSettled: () => client.invalidateQueries({ queryKey: ['approvals'] }),
  })
}

export function useMetrics(window: MetricsWindow) {
  return useQuery({ queryKey: ['metrics', window], queryFn: () => api<Metrics>(`/api/metrics?window=${window}`), refetchInterval: 5_000 })
}

export function useBudgets() {
  return useQuery({ queryKey: ['budgets'], queryFn: () => api<BudgetStatus[]>('/api/budgets'), refetchInterval: 5_000 })
}

/** JSON merge-patch on policy.yaml. The file stays the source of truth: the backend writes it, then reloads it. */
export function usePatchPolicy() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (patch: Record<string, unknown>) =>
      api<{ version: string }>('/api/policy', { method: 'PATCH', headers: adminHeaders(), body: JSON.stringify(patch) }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['policy'] })
      void client.invalidateQueries({ queryKey: ['health'] })
    },
  })
}

export function useScenarios() {
  return useQuery({ queryKey: ['scenarios'], queryFn: () => api<DemoScenario[]>('/api/demo/scenarios'), staleTime: Infinity })
}

export function useDemoRuns() {
  return useQuery({
    queryKey: ['demo-runs'],
    queryFn: () => api<DemoRun[]>('/api/demo/runs'),
    // poll fast only while something is running
    refetchInterval: (query) => (query.state.data?.some((r) => r.status === 'running') ? 600 : 5_000),
  })
}

export function useRunScenario() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (scenario: string) =>
      api<DemoRun>('/api/demo/run', { method: 'POST', headers: adminHeaders(), body: JSON.stringify({ scenario }) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['demo-runs'] }),
  })
}
