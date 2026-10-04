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
    agents: Record<string, EffectiveAgent>
  }
  raw: RawPolicy // as written in policy.yaml: null = inherited
}

export interface EffectiveAgent {
  id: string
  mode: 'monitor' | 'enforce'
  strictness: 'low' | 'medium' | 'high'
  models_allowed: string[]
  tools_allowed: string[]
  tools_need_approval: string[]
  budget: { tokens_per_day: number | null; usd_per_day: number | null; max_tool_calls_per_task: number | null }
  injection_threshold: number
  injection_gate: number
  loop_max_repeats: number
  pii_out_action: string
  judge_enabled: boolean
}

export interface RawPolicy {
  mode: 'monitor' | 'enforce'
  strictness: 'low' | 'medium' | 'high'
  block_status_code: number
  controls: {
    pii: { action: string; outbound_action: string | null; tool_args_action: string; entities: string[] }
    prompt_injection: { action: string; threshold: number | null; monitor_below: number; gate: number | null }
    llm_judge: { enabled: boolean; model: string }
    output_tool_calls: { action: string }
    signatures: { feed: string; url: string | null; refresh_s: number }
  }
  agents: Record<string, { description: string; mode: 'monitor' | 'enforce' | null; strictness: 'low' | 'medium' | 'high' | null }>
}

export type MetricsWindow = '15m' | '1h' | '24h'

export interface Metrics {
  window: MetricsWindow
  totals: {
    requests: number
    allow: number
    redact: number
    block: number
    needs_approval: number
    monitor_only: number
    errors: number
  }
  top_categories: { category: string; count: number }[]
  latency: { check: string; tier: number; p50: number; p95: number; runs: number }[]
  tier_reach: { t2_pct: number; t3_pct: number }
  overhead_ms: { p50: number; p95: number }
  timeseries: { ts: string; allow: number; redact: number; block: number }[]
}

export interface BudgetStatus {
  agent_id: string
  tokens: { used: number; limit: number | null }
  usd: { used: number; limit: number | null; virtual: boolean }
  by_model: { model: string; tokens: number; usd: number }[]
  rate: { rpm: number; limit: number }
  blocked_today: number
  resets_in_s: number
}

export interface DemoScenario {
  name: string
  title: string
  agent: string
  prompt: string
  stops_it: string
  steps: { kind: 'tool' | 'chat'; label: string; note: string; expect: string }[]
}

export interface DemoRun {
  id: string
  scenario: string
  title: string
  agent: string
  task_id: string
  status: 'running' | 'done' | 'error'
  started_at: string
  finished_at: string | null
  error: string | null
  steps: {
    index: number
    kind: 'tool' | 'chat'
    label: string
    note: string
    expect: string
    status: 'pending' | 'running' | 'done'
    decision: string | null
    text: string | null
  }[]
}
