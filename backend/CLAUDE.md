# Backend: AgentGuard gateway (FastAPI, Python 3.13)

One FastAPI service that hosts both entry points (LLM Gateway + MCP Proxy), the check pipeline, the audit log, and the dashboard API.
Design docs: [docs/](docs/README.md). Start with [docs/implementation-plan.md](docs/implementation-plan.md).

## Commands

```bash
source venv/bin/activate
pip install -r requirements.txt            # add requirements-ml.txt for semantic checks
uvicorn app.main:app --reload --port 8000  # OpenAPI at /docs
pytest -q                                  # must pass with no Ollama, no internet
pytest -q -k attacks                       # one test group
python -m demo.agent --scenario injection  # demo agent (needs the stack running)
```

## Target layout

```
app/
  main.py            FastAPI app, router wiring, lifespan (load policy, start watcher, open DB)
  config.py          env settings (pydantic-settings): OLLAMA_URL, POLICY_PATH, DB_PATH, LLM_PROVIDER...
  api/
    llm.py           POST /v1/chat/completions, GET /v1/models (OpenAI-compatible)
    mcp.py           POST /mcp/{server}: JSON-RPC MCP proxy
    events.py        GET /api/events/stream (SSE), GET /api/events
    admin.py         /api/metrics, /api/policy, /api/budgets, /api/approvals, /api/audit/export
  core/
    context.py       RequestContext (agent, channel, payload, trace_id, findings, timings)
    pipeline.py      runs checks in tiers, short-circuits, combines the decision
    decision.py      Finding, CheckResult, Decision, combine()
  policy/
    models.py        pydantic schema of policy.yaml
    store.py         load + validate + version hash + atomic swap
    watcher.py       watchfiles loop → store.reload()
  checks/            one file per check, each `async def run(ctx, policy) -> CheckResult`
    auth.py tool_acl.py model_allowlist.py signatures.py secrets.py pii.py
    budget.py loop.py injection.py judge.py output.py
  providers/
    ollama.py        httpx client to Ollama's OpenAI-compatible API
    mock.py          deterministic fake LLM for tests / offline demo
  audit/
    store.py         SQLite (aiosqlite) + JSONL append
    bus.py           in-process pub/sub that feeds SSE subscribers
  approvals.py       pending human-approval queue (asyncio futures)
demo/
  agent.py           tool-calling loop: openai SDK → gateway, MCP client → proxy
  mcp_servers/       crm.py, email.py, bank.py (FastMCP, streamable HTTP, json_response)
  scenarios.py       benign / injection / pii_leak / runaway_loop
tests/
  cases/*.yaml       data-driven allow / block / redact cases
  test_controls.py test_attacks.py test_budget.py test_hot_reload.py test_mcp_proxy.py
```

## Conventions

- **Every check is a pure-ish async function** with the same signature and returns `CheckResult(findings, decision, score, latency_ms)`. No check calls another check. Ordering and gating belong to `pipeline.py` only.
- **Tiers**: `T0` identity/policy/ACL/budget pre-check → `T1` deterministic (signatures, secrets, PII, loop) → `T2` semantic (DeBERTa injection), gated → `T3` LLM judge, gated. If a tier blocks, the next tier is skipped.
- **Mode `monitor`** never blocks. It records what *would* have happened (`monitor_only: true`).
- **Redaction** replaces spans with typed placeholders: `[EMAIL_1]`, `[IBAN_1]`. Keep the original only in the audit DB, never in the forwarded payload.
- **ML models load lazily and degrade gracefully.** If the model is missing, log a warning and fall back to the heuristic (signatures). Never crash the gateway because of a model.
- **Tests never hit Ollama or Hugging Face.** Use `LLM_PROVIDER=mock` and monkeypatch the classifier.
- Every check writes its latency into `ctx.timings`. Metrics and the dashboard p50/p95 depend on it.
- Use `httpx.AsyncClient` (shared, created in lifespan) for upstream calls. No `requests`.
- Type hints everywhere. Pydantic models for every request/response body.
- AuditEvent schema changes must be mirrored in `frontend/src/types/api.ts`.

## Gotchas

- Ollama already serves an OpenAI-compatible API at `{OLLAMA_URL}/v1/chat/completions`, so forward to it directly.
- `stream: true`: the MVP buffers the upstream response, runs output checks, then re-emits it as SSE chunks.
- Mock MCP servers must use the streamable HTTP transport with `json_response=True, stateless_http=True` so the proxy can treat every call as plain JSON-RPC over POST.
- `tools/list` responses are **filtered** to the agent's allowlist (least privilege: the agent never sees forbidden tools).
- The policy reload must be atomic: validate first, then swap the reference. If the YAML is invalid, keep the old policy and emit a `policy_error` event.
