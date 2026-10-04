# Backend: AgentGuard gateway (FastAPI, Python 3.13)

One FastAPI service that hosts both entry points (LLM Gateway + MCP Proxy), the check pipeline, the audit log, and the dashboard API.
Design docs: [docs/](docs/README.md). Start with [docs/implementation-plan.md](docs/implementation-plan.md).

## Commands

```bash
source venv/bin/activate
pip install -r requirements-dev.txt -r requirements-ml.txt   # runtime + pytest + ONNX classifier
python scripts/download_models.py          # T2 model (~740 MB) into models/, prints its sha256 (`make models`)
python scripts/bench.py                    # overhead benchmark (`make bench`)
uvicorn app.main:app --reload --port 8000  # OpenAPI at /docs
pytest -q                                  # must pass with no Ollama, no internet
pytest -q -k attacks                       # one test group
python -m demo.mcp_servers                 # mock CRM/Email/Bank on :9001-9003
python -m demo.agent --scenario injection  # demo agent (needs gateway + mock servers); --list, --mode llm
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
    (as built: gates.py = model allowlist + tool ACL, budget.py = rate/budget/task/loop,
     signatures.py = feed + banned topics, pii.py, secrets.py, redact.py)
  providers/
    ollama.py        httpx client to Ollama's OpenAI-compatible API
    mock.py          deterministic fake LLM for tests / offline demo
  audit/
    store.py         SQLite (aiosqlite) + JSONL append
    bus.py           in-process pub/sub that feeds SSE subscribers
  approvals.py       pending human-approval queue (asyncio futures)
  ml/                injection.py (ONNX classifier, T2), judge.py (Granite Guardian via Ollama, T3)
  checks/semantic.py T2/T3 checks + their gates, output tool-call check
  providers/auto.py  Ollama when reachable, mock LLM otherwise (the default, LLM_PROVIDER=auto)
  api/prometheus.py  GET /metrics
scripts/             download_models.py, bench.py
Dockerfile           gateway + mock MCP image (build context = repo root; model baked in)
demo/
  agent.py           tool-calling loop: openai SDK → gateway, MCP client → proxy
  mcp_servers/       crm.py, email_service.py, bank.py, data.py; __main__ runs all three (MCPServer, stateless, json_response)
  scenarios.py       benign / injection / pii_leak / runaway_loop
tests/
  cases/*.yaml       data-driven allow / block / redact cases
  test_controls.py test_attacks.py test_budget.py test_hot_reload.py test_mcp_proxy.py
```

## Conventions

- **Every check is an async function** `run(ctx, rt) -> CheckResult` (`rt` = policy snapshot + feed + state), registered in `app/checks/__init__.py` with its tier and stages. No check calls another check. Ordering, gating and timing belong to `core/pipeline.py` only.
- **Tiers**: `T0` identity/policy/ACL/budget pre-check → `T1` deterministic (signatures, secrets, PII, loop) → `T2` semantic (DeBERTa injection), gated → `T3` LLM judge, gated. If a tier blocks, the next tier is skipped.
- **Mode `monitor`** never blocks. It records what *would* have happened (`monitor_only: true`).
- **Redaction** replaces spans with typed placeholders: `[EMAIL_1]`, `[IBAN_1]`. Keep the original only in the audit DB, never in the forwarded payload.
- **ML models load lazily and degrade gracefully.** If the model is missing, log a warning and fall back to the heuristic (signatures). Never crash the gateway because of a model.
- **Tests never hit Ollama or Hugging Face.** Use `LLM_PROVIDER=mock` and monkeypatch the classifier.
- The pipeline writes every check's latency into `ctx.timings`. Metrics and the dashboard p50/p95 depend on it.
- Use `httpx.AsyncClient` (shared, created in lifespan) for upstream calls. No `requests`.
- Type hints everywhere. Pydantic models for every request/response body.
- AuditEvent schema changes must be mirrored in `frontend/src/types/api.ts`.

## Gotchas

- Tests run with `ml_enabled=False, judge_enabled=False`; semantic behaviour is tested with fakes in `tests/test_semantic.py`,
  plus one real-model test that is skipped when `models/` is empty.
- Expensive checks get a `gate=`; never call a model from a check without one.
- Feed the classifier prose, never JSON: it scores JSON structure as an injection (see `semantic.classifiable`).
- `docker compose run` inherits the service env (MCP_HOST...); tests clear it (`hermetic_env`), `make test-docker` uses `docker run`.

- **MCP SDK is 2.x**: `FastMCP` is now `mcp.server.mcpserver.MCPServer`; the client is
  `mcp.client.streamable_http.streamable_http_client(url, http_client=create_mcp_http_client(headers=...))` and uses `httpx2`.
- The MCP servers' lifespan opens anyio task groups: enter and exit it in the same task (see `tests/test_attacks.py`).
- Every scripted demo step has an `expect`; changing policy or signatures can break `tests/test_attacks.py`, which is the point.

- Ollama already serves an OpenAI-compatible API at `{OLLAMA_URL}/v1/chat/completions`, so forward to it directly.
- `stream: true`: the MVP buffers the upstream response, runs output checks, then re-emits it as SSE chunks.
- Mock MCP servers must use the streamable HTTP transport with `json_response=True, stateless_http=True` so the proxy can treat every call as plain JSON-RPC over POST.
- `tools/list` responses are **filtered** to the agent's allowlist (least privilege: the agent never sees forbidden tools).
- The policy reload must be atomic: validate first, then swap the reference. If the YAML is invalid, keep the old policy and emit a `policy_error` event.
