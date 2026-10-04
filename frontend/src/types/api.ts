// Mirrors backend/docs/api-contract.md. Change both together.

export type Decision = 'allow' | 'redact' | 'block' | 'needs_approval'
export type Channel = 'llm' | 'mcp'
export type Direction = 'request' | 'response'
export type Severity = 'low' | 'medium' | 'high' | 'critical'

export interface Finding {
  check: string
  rule_id: string
  category: string
  severity: Severity
  score: number
  message: string
  span?: { start: number; end: number; field?: string | null } | null
}

export interface CheckTiming {
  check: string
  tier: number
  ms: number
  skipped_reason?: string | null
}

export interface ToolRef {
  server: string
  name: string
  arguments?: Record<string, unknown> | null
}

export interface AuditEvent {
  id: string
  ts: string
  trace_id: string
  task_id: string
  agent_id: string
  channel: Channel
  direction: Direction
  model?: string | null
  tool?: ToolRef | null
  decision: Decision
  monitor_only: boolean
  would_have?: Decision | null
  risk: number
  findings: Finding[]
  summary: string
  original_text?: string | null // only from GET /api/events/{id}
  redacted_text?: string | null
  timings: CheckTiming[]
  total_ms: number
  upstream_ms?: number | null
  tokens?: { prompt: number; completion: number } | null
  cost_usd?: number | null
  cost_virtual?: boolean | null
  approval_id?: string | null
  error?: string | null
  policy_version: string
}

export interface EventPage {
  items: AuditEvent[]
  next_before: string | null
}

export type ApprovalStatus = 'pending' | 'approved' | 'denied' | 'timeout'

export interface Approval {
  id: string
  created_at: string
  expires_at: string
  agent_id: string
  tool: ToolRef
  risk: number
  findings: Finding[]
  status: ApprovalStatus
  note?: string | null
}

export type SystemEvent =
  | { type: 'policy_reloaded'; old_version: string; new_version: string; summary: string; ts: string }
  | { type: 'policy_error'; message: string; line?: number | null; ts: string }
  | { type: 'approval_requested'; approval: Approval }
  | { type: 'approval_resolved'; approval_id: string; decision: 'approve' | 'deny' | 'timeout' }
  | { type: 'feed_updated'; feed_version: string; count: number; ts: string }

export interface Health {
  status: string
  environment: string
  llm: 'ollama' | 'mock' | 'offline'
  ml: 'loaded' | 'loading' | 'unavailable' | 'disabled' // T2 injection classifier
  ml_detail: string
  judge: 'available' | 'unavailable' | 'disabled' // T3 LLM judge (Ollama)
  policy_version: string
  feed_version: string
  signatures: number
}

export interface PolicyResponse {
  version: string
  yaml: string
  effective: {
    mode: 'monitor' | 'enforce'
    strictness: 'low' | 'medium' | 'high'
    feed: { version: string; signatures: number }
    agents: Record<string, Record<string, unknown> & { mode: string; strictness: string }>
  }
}
