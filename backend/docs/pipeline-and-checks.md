# Pipeline and Checks

## Check interface

```python
class Check(Protocol):
    name: str            # "pii", "secrets", ...
    tier: Literal[0, 1, 2, 3]
    applies_to: set[Literal["llm_in", "llm_out", "mcp_call", "mcp_result"]]
    run: Callable[[RequestContext, Runtime], Awaitable[CheckResult]]  # Runtime = policy snapshot + signature feed + state
```
`CheckResult = {decision, findings[], replacements: {text index → redacted text}}`. The pipeline measures latency
and records `CheckTiming {check, tier, ms, skipped_reason?}`; checks never time themselves. A check that raises is
recorded as a `CHECK-ERROR` finding and treated as allow (fail open), so one broken rule cannot take the gateway down.

The pipeline (`core/pipeline.py`) is the only place that knows about ordering, gating and short-circuiting.

## Tiers and gating

| Tier | Checks | Always runs? | Latency budget (p95) |
|---|---|---|---|
| T0 gates | auth, model_allowlist, tool_acl, budget pre-check, rate limit, loop | yes | < 1 ms |
| T1 rules | signatures, secrets, pii, banned_topics | yes | < 3 ms |
| T2 classifier | injection (DeBERTa ONNX) | **gated** | < 40 ms CPU |
| T3 judge | llm_judge (Granite Guardian via Ollama) | **gated** | < 1.5 s |

**Gating rule for T2** (any one is enough):
- `risk_after_T1 >= controls.prompt_injection.gate` (default 0.3), or
- the channel is `mcp_result` (tool output = indirect-injection surface) **and** the text is longer than 40 chars, or
- the call targets a tool in `tools_need_approval` / `high_risk_tools`, or
- the agent's `strictness: high`.

**Gating rule for T3:** `controls.llm_judge.enabled` **and** (`risk in [only_for_risk_above, block_threshold)`, the uncertain band, **or** a high-risk tool call). Never run T3 when T1/T2 already block.

This is the performance story: most benign traffic stops after T1 (~1–3 ms).

## Risk score

`risk = 1 - Π(1 - wᵢ·sᵢ)` over the findings (noisy-OR). `sᵢ` is the finding score in [0,1] and `wᵢ` is a severity weight
(`low 0.3`, `medium 0.6`, `high 0.9`, `critical 1.0`). This is simple, explainable, and stays monotonic as findings are added.
The final decision still comes from the **actions** configured per control. The risk score drives gating and display only.

## Decision combination

`block > needs_approval > redact > allow`. In `mode: monitor` (global or per agent), every `block`/`needs_approval`
becomes `allow` with `monitor_only: true` and `would_have: <decision>`. Redactions are still applied in monitor mode,
unless `controls.pii.monitor_redacts: false`.

## Checks

### auth (T0)
`Authorization: Bearer <key>` (LLM) or `X-Agent-Key` (MCP) → SHA-256 → look up `agents[*].key_sha256`. An unknown key
→ 401 + an audit event with `agent_id: "unknown"`. Optional: an `allowed_channels` list per agent.

### model_allowlist (T0, llm_in)
The request `model` must be in `models_allowed` (global or per agent). Supply chain: for HF models loaded by the gateway
itself (the classifier), verify the SHA-256 of the files against `supply_chain.pinned` at load time and refuse to load on mismatch.
Bonus: `checks/picklescan` runs on any `.bin/.pt` files in `models/` at startup.

### tool_acl (T0, mcp_call)
The tool must be in `tools_allowed` → allow. If it is in `tools_need_approval` → `needs_approval`. Otherwise → block `TOOL-NOT-ALLOWED`.
Optional per-tool argument constraints: `send_email.to` must match `@ourbank\.com$`, and `transfer_money.amount <= 1000`.

### budget / rate / loop (T0)
See implementation-plan Step 6. Findings: `BUDGET-TOKENS`, `BUDGET-USD`, `RATE-LIMIT`, `LOOP-DETECTED`, `TASK-TOOL-CALLS`.

### signatures (T1, all directions)
`feeds/signatures.json`:
```json
{ "version": "2026-10-01", "signatures": [
  { "id": "EXEC-OS-SYSTEM", "category": "code_execution", "severity": "critical",
    "pattern": "\\bos\\.system\\s*\\(", "applies_to": ["mcp_call", "llm_in"], "action": "block",
    "description": "Python os.system call in tool args" } ] }
```
Categories to ship (≥ 40 signatures in total):
- **code_execution**: `os.system`, `subprocess`, `eval(`, `exec(`, `__import__`, shell metacharacters in args (`;`, `&&`, `|`, `` ` ``, `$(`).
- **deserialization**: `__reduce__`, pickle opcodes (`cos\nsystem`, `c__builtin__`), `torch.load(`, `yaml.load(` without SafeLoader.
- **ssrf_exfil**: `169.254.169.254`, `metadata.google.internal`, `file://`, `gopher://`, `localhost`/RFC1918 in URL args, markdown image exfil `!\[.*\]\(https?://[^)]*\?[^)]*=` in outputs.
- **path_traversal**: `../`, `..\\`, `%2e%2e%2f`, `/etc/passwd`.
- **jailbreak**: DAN, "developer mode", "ignore (all )?(previous|prior) instructions", "you are now", "system prompt:" impersonation.
- **supply_chain**: unknown `huggingface.co/<org>` repos in args, `pip install` from URLs.
- **indirect_injection**: imperative instructions aimed at the assistant inside `mcp_result` ("assistant, call", "SYSTEM:", hidden HTML comments, zero-width characters).

Precompile all patterns into one regex per channel at load time. Normalise text first: NFKC, strip zero-width characters, collapse whitespace, and decode obvious URL/base64 fragments (best-effort, length-capped).

### secrets (T1)
Patterns: AWS `AKIA[0-9A-Z]{16}`, GitHub `gh[pousr]_[A-Za-z0-9]{36}`, Slack `xox[baprs]-`, OpenAI-style `sk-[A-Za-z0-9]{20,}`,
`-----BEGIN .*PRIVATE KEY-----`, JWT `eyJ[\w-]+\.[\w-]+\.[\w-]+`, generic `(?i)(password|secret|token)\s*[:=]\s*\S{8,}` plus a Shannon entropy > 3.5 filter.
Default action: **block** inbound, **redact** outbound.

### pii (T1)
Entities: EMAIL, PHONE (E.164 and common EU formats), IBAN (mod-97 validated), CREDIT_CARD (Luhn), optional PERSON (Presidio NER).
Redact with stable placeholders per request: `anna@x.com` → `[EMAIL_1]`, and the same value maps to the same placeholder.
The mapping is kept in `ctx.redactions` (the audit DB only), never forwarded.

### banned_topics (T1)
A keyword/regex list per policy (`controls.banned_topics.terms`). Cheap. It is the "business policy" example.

### injection (T2)
DeBERTa classifier → `score = P(injection)`. `score >= threshold` (0.85) → action (block). `monitor_below` (0.6) ≤ score < threshold → a finding only.
On `mcp_result`, the action is `sanitize`: replace the tool result text with
`"[AgentGuard removed content from tool result: suspected prompt injection]"` so the agent keeps working.

### llm_judge (T3)
Prompt to Granite Guardian with the risk name (`harm`, `jailbreak`, `function_call`, `groundedness`/relevance for outputs).
Parse Yes/No → score 0.95 / 0.05. Cache by `sha256(text + risk)` for 10 min (the demo repeats prompts).

### output checks (llm_out, mcp_result)
The same PII/secrets/signatures checks run on responses, plus: exfil links in markdown, and secrets that echo back from tool results.
For LLM output, if the response contains `tool_calls`, run `tool_acl` + `signatures` on the proposed calls **before** the agent executes them.
This is an early warning even when the agent does not use our MCP proxy.

## Strictness presets

| Setting | low | medium (default) | high |
|---|---|---|---|
| injection threshold | 0.95 | 0.85 | 0.70 |
| T2 gate (risk) | 0.5 | 0.3 | always |
| judge band | off | 0.5–0.85 | 0.3–0.85 + all tool calls |
| PII action | redact | redact | block in LLM answers (tool results still redacted) |
| loop max_repeats | 8 | 5 | 3 |

Explicit values in a control override the preset.
