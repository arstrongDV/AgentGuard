import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { Approval, ApprovalStatus, AuditEvent, Health, PolicyResponse } from '../types/api'
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
