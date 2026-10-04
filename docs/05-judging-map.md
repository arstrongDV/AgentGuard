# 05: Judging Map (criterion → feature → evidence)

Every criterion needs **something a judge can see or run**. Before submission, tick the evidence column.

| Criterion (weight) | What we build | Evidence a judge can check | ✓ |
|---|---|---|---|
| **Guardrails (30%)** | Layered checks: identity, model allowlist, tool ACL, filtered `tools/list`, approvals, PII redact, secrets block, signatures (code exec, deserialization, SSRF/exfil, path traversal, jailbreaks, supply chain), injection classifier, LLM judge, indirect injection in tool results | The 3 attacks in `make demo`; Live Feed drawer shows the rule ID + score; `tests/cases/*.yaml` | ☐ |
| **Architecture & performance (20%)** | Tiered pipeline, gating of ML, shared async HTTP client, ONNX classifier, per-check timings | `make bench` table in the README (p50/p95 per check, % reaching T2/T3); Overview latency chart; architecture diagram | ☐ |
| **Reporting (20%)** | Audit SQLite + JSONL, SSE live feed, Overview / Budgets / Audit pages, CSV/JSONL export | Dashboard; `GET /api/audit/export?format=csv` | ☐ |
| **Tests (15%)** | 50+ data-driven YAML cases (allow / block / redact / needs_approval) + budget, loop, hot-reload, MCP proxy tests | `make test` output (offline, green, case count printed) | ☐ |
| **Scalability (15%)** | Stateless handlers + `StateStore` interface, OpenAI-compatible drop-in, external policy + feed files, MCP proxy works with any MCP server | README "Scaling" section; `base_url` one-line diff; feed URL config | ☐ |

## Requirement checklist from the brief

- [ ] Policy engine: `policy.yaml`, reloaded on save, `monitor | enforce`, strictness levels
- [ ] Deterministic checks: PII, secrets, banned topics, tool allowlists, auth
- [ ] Semantic checks: prompt injection, harmful content, output relevance (judge)
- [ ] Budgets: tokens/day, $ cost table incl. virtual cost for local models, compute time, rate limit, loop detection
- [ ] Historical attacks: signature feed from a file or URL with auto refresh. Categories: code exec, unsafe deserialization, supply chain (model allowlist + SHA-256 pinning), SSRF/exfil, path traversal, jailbreak templates, indirect injection
- [ ] Reporting: live metrics, audit export, per-check latency
- [ ] Tests: positive and negative YAML cases, pytest parametrized
- [ ] `docker compose up` + `make test` work on the first try; no paid APIs; English submission
