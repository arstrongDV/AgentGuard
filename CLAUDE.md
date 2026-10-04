# AgentGuard: AI Firewall for LLM agents (Hackathon 2026)

AgentGuard is a security gateway that sits between AI agents and everything they talk to:
- **LLM Gateway**: an OpenAI-compatible `/v1/chat/completions` that forwards to local Ollama. Agents integrate by changing only `base_url`.
- **MCP Proxy**: sits between agents and MCP tool servers and checks every `tools/call` (who is calling, which tool, what arguments, what comes back).

Both entry points run the same **check pipeline**: identity → policy → deterministic checks → semantic checks (only when needed) → budget/loop → forward → output checks → audit. A React dashboard shows the audit stream live over SSE.

The plan and design live in [docs/](docs/README.md). Read it before making architectural changes.

## Repo layout

```
backend/            FastAPI gateway + MCP proxy + checks + audit   → backend/CLAUDE.md
  app/              Python package (entry: app.main:app)
  demo/             demo agent + mock MCP servers (CRM, Email, Bank)
  tests/            pytest + YAML test cases
frontend/           React + TS + Vite dashboard                    → frontend/CLAUDE.md
policy.yaml         THE policy file (hot-reloaded; judges edit it live)
feeds/              signatures.json (historical attack signatures)
docs/               project-wide plan, architecture, roadmap, demo script
docker-compose.yml  ollama + backend + mock MCP servers + frontend
Makefile            make up / make test / make demo / make lint
```
(Some of these are still to be built. See [docs/03-roadmap.md](docs/03-roadmap.md).)

## Commands

```bash
# backend
cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000
cd backend && pytest -q
# frontend
cd frontend && npm run dev        # http://localhost:5173
cd frontend && npm run build && npm run lint
# whole stack (target)
docker compose up    # must work on first try
make test            # must pass WITHOUT Ollama or network
```

## Non-negotiable rules (hackathon constraints)

1. **No paid APIs.** Everything runs locally: Ollama, HF models, and local files. Never add OpenAI, Anthropic or other cloud calls.
2. **`docker compose up` and `make test` must work on the first try** on a clean machine. Tests must not need Ollama, GPU, or internet: stub the LLM and the ML models.
3. **All submission text is in English**: code, comments, README, docs, UI.
4. **Check model licenses** before adding a model. Prefer Apache-2.0/MIT (DeBERTa injection classifier, Granite Guardian). Llama Guard / Prompt Guard use the Llama license, so note this in the README if you use them.
5. **The policy file is the single source of truth.** The dashboard edits the policy by writing `policy.yaml`. The watcher reloads it. Never keep policy state that is not in the file.
6. **Cheap checks first, AI only when needed.** Deterministic checks always run (~1 ms). Semantic models run only when the risk is uncertain or the action is high-risk. Every check reports its latency.

## Cross-cutting contracts

- **AuditEvent** is the shared shape between backend and frontend. Its schema is defined in [backend/docs/api-contract.md](backend/docs/api-contract.md). If you change it, update `frontend/src/types/api.ts` in the same change.
- **Decision values**: `allow | redact | block | needs_approval` (plus `monitor_only: true` when policy `mode: monitor`). Severity order for combining: `block > needs_approval > redact > allow`.
- Agent identity comes from the `Authorization: Bearer <agent-key>` header (LLM) or the `X-Agent-Key` header (MCP).

## Working style

- Keep the submission demo-able at every commit. Main must always run.
- Prefer small, boring, readable code over clever abstractions. Judges read it.
- When adding a check, also add positive and negative YAML test cases in `backend/tests/cases/`.
