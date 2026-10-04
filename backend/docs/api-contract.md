# API Contract (backend ↔ frontend ↔ agents)

**Freeze this at hour 0.** Additive changes are OK. Breaking changes need both owners to agree and must update
`frontend/src/types/api.ts` in the same commit.

## Agent-facing

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/v1/chat/completions` | `Bearer <agent key>` | OpenAI-compatible. `stream` supported (buffered). Response headers: `x-agentguard-decision`, `x-agentguard-trace-id`, `x-agentguard-risk` |
| GET | `/v1/models` | `Bearer <agent key>` | Allowed models for this agent |
| POST | `/mcp/{server}` | `X-Agent-Key` | MCP JSON-RPC proxy (see mcp-proxy.md) |

Optional request header for both: `X-AgentGuard-Task: <id>` groups calls into a task for budgets and loop detection.

## Dashboard-facing (`/api`)

Read endpoints are open in dev. Mutations need `Authorization: Bearer <ADMIN_TOKEN>`.

| Method | Path | Returns |
|---|---|---|
| GET | `/health` | `{status, environment, llm: "ollama"|"mock"|"offline", ml: "loaded"|"unavailable", policy_version}` |
| GET | `/api/events?limit=100&before=<ts>&agent=&decision=&category=` | `{items: AuditEvent[], next_before}` |
| GET | `/api/events/stream` | SSE. `event: audit` → AuditEvent; `event: system` → SystemEvent; `event: ping` every 15 s |
| GET | `/api/events/{id}` | AuditEvent (full, including originals) |
| GET | `/api/metrics?window=15m\|1h\|24h` | Metrics |
| GET | `/api/budgets` | BudgetStatus[] |
| GET | `/api/policy` | `{version, yaml: string, effective: object}` |
| PATCH | `/api/policy` | JSON merge-patch → `{version}` or 422 `{error, path}` |
| GET | `/api/approvals?status=pending` | Approval[] |
| POST | `/api/approvals/{id}` | body `{decision: "approve"|"deny", note?}` |
| GET | `/api/audit/export?format=csv\|jsonl&from=&to=&agent=` | file download (streamed) |
| POST | `/api/demo/run` *(stretch)* | body `{scenario, agent}`, which runs the demo agent in the background |

## Types

```ts
type Decision = "allow" | "redact" | "block" | "needs_approval";
type Channel = "llm" | "mcp";
type Direction = "request" | "response";
type Severity = "low" | "medium" | "high" | "critical";

interface Finding {
  check: string;            // "pii" | "secrets" | "signatures" | "injection" | "judge" | "tool_acl" | "budget" | "loop" | ...
  rule_id: string;          // "PII-EMAIL", "EXEC-OS-SYSTEM", "TOOL-NOT-ALLOWED", "LOOP-DETECTED"
  category: string;         // "pii" | "secret" | "code_execution" | "ssrf_exfil" | "prompt_injection" | "budget" | ...
  severity: Severity;
  score: number;            // 0..1
  message: string;
  span?: { start: number; end: number; field?: string };
}

interface CheckTiming { check: string; tier: 0 | 1 | 2 | 3; ms: number; skipped_reason?: string }

interface AuditEvent {
  id: string;               // ulid
  ts: string;               // ISO 8601
  trace_id: string;
  task_id: string;
  agent_id: string;
  channel: Channel;
  direction: Direction;
  model?: string;
  tool?: { server: string; name: string; arguments?: Record<string, unknown> };
  decision: Decision;
  monitor_only: boolean;
  would_have?: Decision;    // set when monitor_only
  risk: number;             // 0..1
  findings: Finding[];
  original_text?: string;   // only in /api/events/{id}, truncated to 8 KB
  redacted_text?: string;
  timings: CheckTiming[];
  total_ms: number;
  upstream_ms?: number;
  tokens?: { prompt: number; completion: number };
  cost_usd?: number;
  cost_virtual?: boolean;
  approval_id?: string;
  policy_version: string;
}

type SystemEvent =
  | { type: "policy_reloaded"; old_version: string; new_version: string; summary: string; ts: string }
  | { type: "policy_error"; message: string; ts: string }
  | { type: "approval_requested"; approval: Approval }
  | { type: "approval_resolved"; approval_id: string; decision: "approve" | "deny" | "timeout" }
  | { type: "feed_updated"; feed_version: string; count: number };

interface Approval {
  id: string; created_at: string; expires_at: string; agent_id: string;
  tool: { server: string; name: string; arguments: Record<string, unknown> };
  risk: number; findings: Finding[]; status: "pending" | "approved" | "denied" | "timeout";
}

interface Metrics {
  window: string;
  totals: { requests: number; allow: number; redact: number; block: number; needs_approval: number; monitor_only: number };
  top_categories: { category: string; count: number }[];
  latency: { check: string; tier: number; p50: number; p95: number; runs: number }[];
  tier_reach: { t2_pct: number; t3_pct: number };
  overhead_ms: { p50: number; p95: number };   // gateway time excluding upstream
  timeseries: { ts: string; allow: number; redact: number; block: number }[];  // 1-min buckets
}

interface BudgetStatus {
  agent_id: string;
  tokens: { used: number; limit: number };
  usd: { used: number; limit: number; virtual: boolean };
  by_model: { model: string; tokens: number; usd: number }[];
  rate: { rpm: number; limit: number };
  blocked_today: number;
}
```

`frontend/public/fixtures/*.json` contains example payloads of each type. Keep them valid; the frontend develops against them.
