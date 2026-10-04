# Backend Implementation Plan

**Status (2026-10-04): all steps are implemented**, including the semantic layer (step 8), Prometheus, `make bench` and
Docker packaging (step 11), verified: `docker compose up`, every demo scenario against the containers, hot reload
from a host edit, 157 tests inside the image. 157 tests pass offline. Remaining ideas, not planned: Redis StateStore, token-by-token
streaming scans, Presidio NER. Earlier notes: Implementation notes that differ from the original plan:
- Audit store uses stdlib `sqlite3` behind a lock instead of `aiosqlite` (sub-millisecond writes, one less dependency).
- SSE is a plain `StreamingResponse`; `sse-starlette` is not needed.
- Policy edits use `ruamel.yaml` round-trip so comments survive dashboard changes.
- Event paging uses the event id (monotonic ULID) as the cursor.

Original starting point: `app/main.py` (FastAPI + CORS + `/health`) and `app/config.py` (pydantic-settings).
We grow this package step by step and keep the app runnable after every step.

## Dependencies

`requirements.txt` (core, always installed, light):
```
fastapi, uvicorn[standard], pydantic-settings, python-dotenv   # existing
httpx            # upstream calls (Ollama, MCP servers)
pyyaml           # policy
watchfiles       # hot reload
aiosqlite        # audit + counters
sse-starlette    # SSE endpoint
mcp              # MCP SDK (client for demo agent) ; fastmcp for mock servers
openai           # demo agent only (talks to OUR gateway, not to OpenAI)
pytest, pytest-asyncio   # (or requirements-dev.txt)
```
`requirements-ml.txt` (optional, heavy, installed in Docker):
```
onnxruntime, transformers (tokenizer only), huggingface_hub
presidio-analyzer, presidio-anonymizer, spacy + en_core_web_sm   # only if we do NER
```
The gateway must import and run **without** `requirements-ml.txt`, in which case the semantic checks report `skipped: model_unavailable`.

## Settings (`app/config.py` additions)

| Env | Default | Purpose |
|---|---|---|
| `POLICY_PATH` | `../policy.yaml` | policy file (mounted in Docker) |
| `FEEDS_DIR` | `../feeds` | signatures feed |
| `DATA_DIR` | `./data` | SQLite + JSONL |
| `LLM_PROVIDER` | `ollama` | `ollama` or `mock` |
| `OLLAMA_URL` | `http://localhost:11434` | |
| `ADMIN_TOKEN` | `dev-admin` | protects `/api/*` mutations |
| `ML_ENABLED` | `true` | allow loading the classifier |

## Steps

### Step 1: Skeleton and contracts (A)
Files: `core/decision.py`, `core/context.py`, `policy/models.py`, `policy/store.py`, `../policy.yaml`.
- `Decision` enum, `Finding(check, rule_id, category, severity, score, message, span)`, `CheckResult`.
- `RequestContext`: `trace_id`, `task_id` (header `X-AgentGuard-Task`, default = trace), `agent`, `channel` (`llm|mcp`), `direction`, `texts` to scan, `findings`, `timings`, `redactions`.
- Pydantic policy schema (see [policy-schema.md](policy-schema.md)). `PolicyStore.current()` returns an immutable snapshot plus a `version` (short SHA-256 of the file bytes).
- **Done when:** `python -c "from app.policy.store import PolicyStore; ..."` loads the sample policy and invalid YAML raises a clear error.

### Step 2: LLM gateway, non-streaming (A)
Files: `providers/ollama.py`, `providers/mock.py`, `api/llm.py`, `core/pipeline.py` (T0 + T1 only).
- `POST /v1/chat/completions`: auth → pipeline(input) → forward → pipeline(output) → audit → response in OpenAI format.
- Block response: HTTP 200 with an assistant message `"[AgentGuard] Request blocked: <category> (<rule_id>)"` plus `x-agentguard-decision: block` header. **Why 200:** agents keep running and show a clean message; also offer `policy.block_status_code: 403` for strict clients.
- `GET /v1/models` returns `models_allowed`.
- The mock provider echoes the input and can be scripted with magic strings (e.g. `__LEAK_PII__` returns a canned answer with PII) so output checks are testable.
- **Done when:** `curl` with the agent key returns a completion via Ollama, and via mock with `LLM_PROVIDER=mock`.

### Step 3: Deterministic checks (B)
Files: `checks/auth.py`, `checks/model_allowlist.py`, `checks/pii.py`, `checks/secrets.py`, `checks/signatures.py`, `../feeds/signatures.json`.
- See [pipeline-and-checks.md](pipeline-and-checks.md) for rules. Validate IBAN (mod-97) and cards (Luhn) to cut false positives.
- **Done when:** the 10 first YAML cases pass.

### Step 4: Audit and events (A)
Files: `audit/store.py`, `audit/bus.py`, `api/events.py`.
- SQLite table `events(id, ts, agent_id, channel, decision, risk, categories, payload_json)` + indexes on `ts` and `agent_id`. Append the same JSON to `audit.jsonl`.
- `EventBus`: a set of `asyncio.Queue`s, publish is non-blocking (drop the oldest event if a subscriber is slow).
- `GET /api/events` (paged, filters) and `GET /api/events/stream` (SSE, sends a heartbeat every 15 s).
- **Done when:** the dashboard fixtures can be replaced by the live endpoint.

### Step 5: MCP proxy + mocks + approvals (C)
Files: `api/mcp.py`, `checks/tool_acl.py`, `approvals.py`, `demo/mcp_servers/*.py`. See [mcp-proxy.md](mcp-proxy.md).
- **Done when:** `tools/list` for support-bot hides `transfer_money`; a `tools/call` with `;rm -rf` in an argument is blocked; `transfer_money` for finance-bot waits for approval.

### Step 6: Budgets, rate limit, loop detection (A)
Files: `checks/budget.py`, `checks/loop.py`, `state.py` (StateStore interface + memory/SQLite implementation).
- Pre-check in T0 (already over the limit → block). Post-accounting after the response (tokens from `usage`, or estimated as chars/4 for the mock).
- Cost = `tokens × price[model]` from `policy.costs`. Local models have a **virtual** price, which is labelled as such in the UI.
- Loop: key = `hash(agent, tool, canonical_json(args))`. Count in a sliding window. Block when ≥ `loop.max_repeats` within `loop.window_s`.
- `max_tool_calls_per_task` counts per `task_id`.
- **Done when:** `test_budget.py` passes: limit hit → block, a new day → reset (inject a clock).

### Step 7: Demo agent (C)
Files: `demo/agent.py`, `demo/scenarios.py`.
- `openai.OpenAI(base_url="http://localhost:8000/v1", api_key=<agent key>)` + MCP client over streamable HTTP to `http://localhost:8000/mcp/{server}`.
- `--mode scripted` (default): a deterministic sequence of tool calls (no LLM reasoning) so the stage demo never depends on model behaviour. `--mode llm` lets a real model drive.
- Pretty terminal output (`rich`): each step shows the AgentGuard decision.

### Step 8: Semantic layer (B)
Files: `checks/injection.py`, `checks/judge.py`.
- Classifier: ONNX export of `protectai/deberta-v3-base-prompt-injection-v2`, loaded lazily in a thread at startup (`asyncio.to_thread` for inference), max 512 tokens, chunk long texts (sliding window, take the max score).
- Judge: Ollama `granite3-guardian` with a short yes/no prompt per risk category. Timeout 3 s. On timeout, apply `policy.controls.llm_judge.on_timeout` (`allow|block`).
- Both are gated (see pipeline doc). Both record `skipped_reason` when not run, so the dashboard can show "% reaching T2/T3".

### Step 9: Hot reload + policy API (A)
Files: `policy/watcher.py`, `api/admin.py`.
- `watchfiles.awatch(POLICY_PATH)` in a lifespan task. On change, parse and validate, then swap, then emit a `policy_reloaded` event (or `policy_error` and keep the old policy).
- Signatures feed: reload on file change, or poll the URL every `refresh_s`, using ETag/If-Modified-Since.
- `PATCH /api/policy` takes a JSON merge-patch, applies it to the YAML (`ruamel.yaml` keeps comments, which is nice to have), writes it atomically (tmp + rename), and lets the watcher reload it.

### Step 10: Metrics, export, bench (A/B)
- `GET /api/metrics?window=15m`: totals, decision breakdown, top categories, p50/p95 per check, tier-reach %.
- `GET /api/audit/export?format=csv|jsonl&from=&to=&agent=`: streamed response.
- `scripts/bench.py`: N requests per class (benign/PII/injection) → markdown table for the README.
- Stretch: Prometheus `/metrics` via `prometheus-client`.

### Step 11: Packaging
- `backend/Dockerfile`: python:3.13-slim, install core + ML requirements, **pre-download the ONNX model at build time**, non-root user.
- Root `docker-compose.yml` + `Makefile` (`up`, `down`, `test`, `demo`, `bench`, `seed`, `lint`).
- `make test` = `docker compose run --rm backend pytest -q`, **or** a local venv when Docker is not available.

## Definition of done (backend)

- `pytest -q` is green offline, with 50+ cases.
- No check takes longer than its latency budget in `make bench` (see the pipeline doc).
- Every decision produces exactly one audit event per direction, with timings for each check that ran.
- Killing Ollama mid-demo results in a clear error event, not a 500 stack trace.
