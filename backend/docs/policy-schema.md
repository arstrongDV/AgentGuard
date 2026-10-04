# Policy Schema (`policy.yaml`)

The policy is the product's main UI for security teams. Keep it **readable**: comments, sane defaults, and short keys.
It lives at the repo root, is mounted into the container, and is hot-reloaded.

## Full example

```yaml
version: 1
mode: enforce                 # monitor | enforce   (global; agents may override)
strictness: medium            # low | medium | high (preset, see pipeline-and-checks.md)
block_status_code: 200        # 200 = friendly assistant message, 403 = hard error

models_allowed: [qwen2.5:7b, llama3.1:8b]

costs:                        # USD per 1K tokens. Local models get a VIRTUAL price (shown as such)
  qwen2.5:7b:  { input: 0.0002, output: 0.0006, virtual: true }
  llama3.1:8b: { input: 0.0002, output: 0.0006, virtual: true }

controls:
  pii:              { action: redact, entities: [EMAIL, IBAN, PHONE, CREDIT_CARD] }
  secrets:          { action: block, outbound_action: redact }
  banned_topics:    { action: block, terms: ["internal salary", "merger plan"] }
  prompt_injection: { action: block, threshold: 0.85, monitor_below: 0.6, gate: 0.3 }
  llm_judge:        { enabled: true, model: granite3-guardian:2b, only_for_risk_above: 0.5, timeout_s: 3, on_timeout: allow }
  signatures:       { feed: ./feeds/signatures.json, url: null, refresh_s: 60 }
  loop:             { max_repeats: 5, window_s: 60 }
  rate_limit:       { requests_per_minute: 60 }

supply_chain:
  pinned:                       # verified at model load time
    protectai/deberta-v3-base-prompt-injection-v2: { sha256: "<model.onnx sha256>" }
  allowed_hf_orgs: [protectai, ibm-granite]

mcp_servers:                    # fixed upstreams: the proxy is never an open relay
  crm:   { url: http://mcp-crm:9001/mcp }
  email: { url: http://mcp-email:9002/mcp }
  bank:  { url: http://mcp-bank:9003/mcp }

high_risk_tools: [transfer_money, send_email]

agents:
  support-bot:
    key_sha256: "<sha256 of demo key>"     # demo key printed in README
    tools_allowed: [search_customers, get_customer, send_email]
    tools_need_approval: []
    tool_args:
      send_email: { to: { pattern: "@ourbank\\.com$" } }
    budget: { tokens_per_day: 200000, usd_per_day: 2.0, max_tool_calls_per_task: 20 }

  finance-bot:
    key_sha256: "<sha256>"
    strictness: high
    tools_allowed: [get_customer, get_balance]
    tools_need_approval: [transfer_money]
    tool_args:
      transfer_money: { amount: { max: 1000 } }
    approval: { timeout_s: 60, on_timeout: deny }
    budget: { tokens_per_day: 100000, usd_per_day: 1.0, max_tool_calls_per_task: 10 }
```

## Pydantic model rules

- `extra="forbid"` everywhere, so a typo in the YAML gives a clear error instead of being silently ignored.
- Agent settings inherit the global `mode`/`strictness` when they are not set.
- Resolve presets at load time into a flat `EffectivePolicy` per agent, so checks never compute the inheritance themselves.
- `version` (the schema version) is different from `policy_version` (a short SHA-256 of the file content, which is shown on every event).

## Hot-reload semantics

1. `watchfiles` sees a change, with a 200 ms debounce (editors write twice).
2. Read → `yaml.safe_load` → validate.
3. On success: swap the snapshot atomically (a single reference assignment), then emit `policy_reloaded {old_version, new_version, diff_summary}`.
4. On failure: keep the old snapshot and emit `policy_error {message, line}`. The dashboard shows a red banner.
5. In-flight requests keep the snapshot they started with (each request takes its snapshot once).
6. Budget counters survive reloads. Changing a limit applies to the current day's accumulated spend.

## Dashboard writes

`PATCH /api/policy` with a JSON merge-patch, e.g. `{"agents": {"support-bot": {"strictness": "high"}}}`.
The backend validates the merged result first, then writes the YAML atomically and lets the watcher do the reload, so the file stays the single
source of truth and a judge watching the file sees the change appear in their editor.
