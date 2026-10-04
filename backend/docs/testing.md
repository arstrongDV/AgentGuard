# Testing

Goal: **50+ cases, green offline in under 30 s**, readable by judges. Tests are worth 15% of the score, so make them visible:
print a summary (`52 cases: 18 allow · 21 block · 9 redact · 4 needs_approval`) at the end of `make test`.

## Rules

- No network, no Ollama, no HF downloads. `conftest.py` sets `LLM_PROVIDER=mock`, `ML_ENABLED=false`, and a temp `DATA_DIR`.
- The classifier and judge are replaced with fakes that score from keywords, so T2/T3 gating logic is still tested.
- Use `httpx.AsyncClient(transport=ASGITransport(app))` against the real FastAPI app (end-to-end through the pipeline).
- Mock MCP servers run **in-process** (an ASGI app mounted via a transport mapping), so there are no ports.
- Inject a clock (`state.now = lambda: ...`) for budget day-rollover and loop windows.

## YAML case format (`tests/cases/*.yaml`)

```yaml
- id: pii-email-redacted
  channel: llm_in            # llm_in | llm_out | mcp_call | mcp_result
  agent: support-bot
  input: "Contact me at anna.schmidt@example.com please"
  expect:
    decision: redact
    rules: [PII-EMAIL]
    contains: "[EMAIL_1]"
    not_contains: "anna.schmidt@example.com"

- id: tool-not-allowed
  channel: mcp_call
  agent: support-bot
  tool: { server: bank, name: transfer_money, arguments: { to_iban: "DE89370400440532013000", amount: 5000 } }
  expect: { decision: block, rules: [TOOL-NOT-ALLOWED] }

- id: benign-question
  channel: llm_in
  agent: support-bot
  input: "What are your opening hours?"
  expect: { decision: allow, max_risk: 0.2 }
```
`test_controls.py` loads every file and parametrizes with `ids=case.id`.

## Case files and target counts

| File | Count | Covers |
|---|---|---|
| `pii.yaml` | 8 | each entity; invalid IBAN/Luhn **not** flagged (negative); output redaction |
| `secrets.yaml` | 6 | AWS, GitHub, private key, JWT; low-entropy "password: 12345" negative |
| `signatures.yaml` | 14 | ≥ 2 per category: code exec, deserialization, SSRF/exfil, path traversal, jailbreak, supply chain |
| `injection.yaml` | 6 | direct, indirect in `mcp_result`, zero-width obfuscated, benign "ignore the typo" negative |
| `tools.yaml` | 8 | ACL allow/block, hidden in tools/list, approval required, arg constraints |
| `benign.yaml` | 10 | normal support questions, which must all be allow (false-positive guard) |

## Non-YAML tests

- `test_budget.py`: token limit, usd limit, rate limit, task tool-call limit, day rollover.
- `test_loop.py`: same call ×N → block; different args → no block; window expiry.
- `test_hot_reload.py`: write a new policy to a temp file → within 2 s the decision changes; invalid YAML → old policy kept + `policy_error`.
- `test_mcp_proxy.py`: tools/list filtering, approval approve/deny/timeout, sanitised tool result.
- `test_monitor_mode.py`: block → allow + `monitor_only` + `would_have`.
- `test_audit.py`: one event per direction, export CSV header, SSE delivers an event.
- `test_attacks.py`: the 3 demo scenarios end to end with the scripted agent.

## Benchmark (`make bench`)

`scripts/bench.py` sends 500 mixed requests (70% benign, 20% PII, 10% attack) using the mock provider, so we measure **gateway
overhead**, not the LLM. It outputs a markdown table: per check p50/p95, the share of requests that reached T2/T3, and total overhead p50/p95.
Run it once with ML enabled in Docker and paste the result into the README.
