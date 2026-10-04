# 03: Roadmap, Team Split, Cut Lines

Hours assume a ~48 h hackathon. Scale them proportionally. The rule: **after every phase the
project must be demo-able**. If time runs out, we ship the last finished phase, not a half-built next one.

## Team split (3–4 people)

| Role | Owns | Primary docs |
|---|---|---|
| **A: Gateway & Policy** | FastAPI app, pipeline, policy store + hot reload, budgets, audit, dashboard API | [backend/docs/pipeline-and-checks.md](../backend/docs/pipeline-and-checks.md), [policy-schema.md](../backend/docs/policy-schema.md) |
| **B: Detection** | PII, secrets, signatures feed, injection classifier, LLM judge, latency numbers | [backend/docs/pipeline-and-checks.md](../backend/docs/pipeline-and-checks.md) |
| **C: Agent, MCP & Tests** | MCP proxy, mock CRM/Email/Bank, demo agent + scenarios, YAML test suite, Makefile, compose | [backend/docs/mcp-proxy.md](../backend/docs/mcp-proxy.md), [testing.md](../backend/docs/testing.md) |
| **D: Dashboard & Pitch** | React console, charts, approvals UI, README, architecture image, slides | [frontend/docs/](../frontend/docs/README.md), [04-demo-script.md](04-demo-script.md) |

With 3 people, merge C into A+B (A takes the MCP proxy, B takes the tests).

**Hour 0 sync (30 min, all together):** freeze the **AuditEvent schema** and the **API contract**
([backend/docs/api-contract.md](../backend/docs/api-contract.md)). After that, the frontend builds against
a fixtures file and never waits on the backend.

## Phases

### Phase 1: Core gateway (h 0–8) · MUST · backend ✅ done
- [ ] `policy.yaml` + pydantic schema + loader (no hot reload yet)
- [ ] `/v1/chat/completions` proxy to Ollama (non-stream) + mock provider
- [ ] API-key → agent identity
- [ ] Regex PII (email, phone, IBAN with mod-97 check, credit card with Luhn check) + secrets (AWS, GitHub, OpenAI-style, private keys, JWT)
- [ ] Decision combiner, redaction placeholders
- [ ] Audit to SQLite + JSONL, `GET /api/events`
- [ ] 10 YAML test cases + pytest runner
- [ ] Frontend: shell, router, `types/api.ts`, Live Feed against fixtures
- **Demo-able:** curl a prompt with an email → it gets redacted, and the event shows up in the feed.

### Phase 2: Agents and tools (h 8–18) · MUST · ✅ done
- [x] Mock MCP servers: CRM (`search_customers`, `get_customer`), Email (`send_email`), Bank (`get_balance`, `transfer_money`)
- [x] MCP proxy: `initialize`, `tools/list` (filtered), `tools/call` (ACL + args checks + result checks)
- [x] Approval queue for `tools_need_approval` (hold the call, approve from the API)
- [x] Budgets: tokens/day, $/day with a virtual-cost table, rate limit, max tool calls per task, loop detection
- [x] Demo agent with the 4 scenarios (benign, injection, pii_leak, runaway_loop)
- [x] SSE `/api/events/stream`; frontend Live Feed goes live; Approvals page
- **Demo-able:** all 3 attacks stopped, visible live.

### Phase 3: Smart layer (h 18–30) · SHOULD · ✅ done
- [x] Signatures feed (`feeds/signatures.json`, file or URL, refresh every N s), covering all categories from the brief
- [x] DeBERTa injection classifier (ONNX, lazy load, gated by risk)
- [x] LLM judge via Ollama Granite Guardian (gated)
- [x] Hot reload with watchfiles + `policy_reloaded` event; `PATCH /api/policy`
- [x] Strictness presets low/medium/high; `mode: monitor | enforce`
- [x] Output checks: markdown-image exfil links, indirect injection inside tool results
- **Demo-able:** a judge edits YAML live and the behaviour changes within a second.

### Phase 4: Reporting and proof (h 30–40) · SHOULD
- [x] Metrics endpoint: counts, block/redact %, top categories, p50/p95 per check, % of requests that reached T2/T3
- [ ] Overview, Budgets, Policy, Audit pages complete; CSV/JSONL export
- [x] 50+ test cases; budget + hot-reload + MCP tests; `make test` green offline
- [x] `docker-compose.yml`, `Makefile`, `make seed` · [ ] architecture diagram PNG · [ ] compose verified end to end on a clean machine
- [x] Benchmark script: `make bench` → latency table pasted into the README

### Phase 5: Polish and pitch (h 40–48) · MUST
- [x] `make demo` runs the 3 attacks with nice terminal output
- [ ] README: 3-minute quick start, screenshots/GIF, architecture, scoring map, limitations, licenses
- [ ] Clean-machine test: fresh clone → `docker compose up` → `make test` (a teammate who did not build it does this)
- [ ] Rehearse the pitch twice with a timer ([04-demo-script.md](04-demo-script.md))
- [ ] Stretch: Attack Lab page (run scenarios from the UI), [x] Prometheus `/metrics`, Redis StateStore

## Cut lines (drop in this order if late)

1. Attack Lab page, Prometheus, Redis
2. Presidio NER (keep the regex PII)
3. LLM judge (keep the DeBERTa classifier; say "pluggable judge" in the pitch)
4. True SSE streaming for completions (buffer and re-emit)
5. **Never cut:** MCP proxy, approvals, budgets/loop, live feed, YAML tests, `docker compose up`

## Top risks and mitigations

| Risk | Mitigation |
|---|---|
| Ollama model download is slow on the judges' machine | Mock provider fallback + seeded data; small models; README shows the pull command |
| HF model download fails in Docker | Download at image build time; fall back to signatures if missing |
| Small local model is bad at tool calling | Use `qwen2.5:7b`; the demo agent can also run **scripted** tool calls (`--mode scripted`, the default) so the attack path is deterministic on stage |
| Integration hell at the end | API contract frozen at hour 0; frontend built on fixtures; integrate daily |
| Flaky live demo | Pre-recorded GIF/video as backup; `make demo` is deterministic |
