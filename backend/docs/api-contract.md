# API Contract (backend ↔ frontend ↔ agents)

**Status: implemented** (except `/api/demo/run`). The shapes below are what the backend returns today.

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
| GET | `/health` | `{status, environment, llm: "ollama"|"mock"|"offline", ml: "loaded"|"loading"|"unavailable"|"disabled", ml_detail, judge: "available"|"unavailable"|"disabled", policy_version, feed_version, signatures}` |
| GET | `/metrics` | Prometheus text format: `agentguard_events_total`, `agentguard_findings_total`, `agentguard_check_skipped_total`, `agentguard_check_latency_ms` (summary), approvals pending, signatures, ML loaded, policy info |
| GET | `/api/events?limit=100&before=<event id>&agent=&decision=&category=` | `{items: AuditEvent[], next_before: string \| null}`, newest first. Paging cursor is an event id (ids sort by time), not a timestamp: many events share a millisecond. Items omit `original_text`/`redacted_text` |
| GET | `/api/events/stream` | SSE. `event: audit` → AuditEvent (without bodies); `event: system` → SystemEvent; `event: ping` every 15 s |
| GET | `/api/events/{id}` | AuditEvent (full, including originals) |
| GET | `/api/metrics?window=15m\|1h\|24h` | Metrics |
| GET | `/api/budgets` | BudgetStatus[] |
| GET | `/api/policy` | `{version, yaml: string, effective: object}` |
| PATCH | `/api/policy` | JSON merge-patch (`null` deletes a key) → `{version}` or 422 `{error, path}`. Comments and layout of `policy.yaml` are preserved |
| GET | `/api/approvals?status=pending\|approved\|denied\|timeout` | Approval[] (pending first, then the most recent 200 resolved) |
| POST | `/api/approvals/{id}` | body `{decision: "approve"|"deny", note?}` → Approval. 404 unknown, 409 already resolved |
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
  summary: string;          // one line for the feed, built from the REDACTED text (≤120 chars) or "server.tool"
  original_text?: string;   // only in /api/events/{id}, truncated to 8 KB
  redacted_text?: string;
  timings: CheckTiming[];
  total_ms: number;
  upstream_ms?: number;
  tokens?: { prompt: number; completion: number };
  cost_usd?: number;
  cost_virtual?: boolean;
  approval_id?: string;
  error?: string;           // upstream failure (LLM or MCP server down). Not a security decision
  policy_version: string;
}

type SystemEvent =
  | { type: "policy_reloaded"; old_version: string; new_version: string; summary: string; ts: string }
  | { type: "policy_error"; message: string; line?: number; ts: string }
  | { type: "approval_requested"; approval: Approval }
  | { type: "approval_resolved"; approval_id: string; decision: "approve" | "deny" | "timeout" }
  | { type: "feed_updated"; feed_version: string; count: number };

interface Approval {
  id: string; created_at: string; expires_at: string; agent_id: string;
  tool: { server: string; name: string; arguments: Record<string, unknown> };
  risk: number; findings: Finding[]; status: "pending" | "approved" | "denied" | "timeout"; note?: string;
}

interface Metrics {
  window: string;
  // requests = request-direction events; decision counts are over all events (request + response)
  totals: { requests: number; allow: number; redact: number; block: number; needs_approval: number; monitor_only: number; errors: number };
  top_categories: { category: string; count: number }[];
  latency: { check: string; tier: number; p50: number; p95: number; runs: number }[];
  tier_reach: { t2_pct: number; t3_pct: number };
  overhead_ms: { p50: number; p95: number };   // gateway time excluding upstream
  timeseries: { ts: string; allow: number; redact: number; block: number }[];  // 1-min buckets (15-min for 24h)
}

interface BudgetStatus {
  agent_id: string;
  tokens: { used: number; limit: number | null };      // null = no limit
  usd: { used: number; limit: number | null; virtual: boolean };
  by_model: { model: string; tokens: number; usd: number }[];
  rate: { rpm: number; limit: number };
  blocked_today: number;
  resets_in_s: number;      // budgets reset at 00:00 UTC
}
```

`frontend/public/fixtures/*.json` contains example payloads of each type. Keep them valid; the frontend develops against them.
