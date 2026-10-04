# Frontend: AgentGuard dashboard (React 19 + TypeScript 6 + Vite 8)

The security console for AgentGuard: posture overview, live event feed, approvals, budgets, policy controls, and audit export.
Design docs: [docs/](docs/README.md). Start with [docs/implementation-plan.md](docs/implementation-plan.md).

## Commands

```bash
npm install
npm run dev       # http://localhost:5173, backend expected at VITE_API_URL (default http://localhost:8000)
npm run build     # tsc -b && vite build. Must pass with zero type errors
npm run lint      # oxlint
```

## Stack (planned additions marked +)

- React 19, TypeScript 6 (strict, `verbatimModuleSyntax`, so use `import type`), Vite 8, oxlint
- + `react-router` for pages
- + `@tanstack/react-query` for REST data (metrics, budgets, policy, approvals)
- + native `EventSource` for the live feed (`/api/events/stream`). No socket libraries.
- + `recharts` for charts
- + `tailwindcss` v4 via `@tailwindcss/vite`
- `react-icons` for icons: `react-icons/lu` (Lucide set) for UI icons, `react-icons/si` (Simple Icons) for brand logos

## Target layout

```
src/
  main.tsx, App.tsx          router + QueryClientProvider + layout shell
  lib/api.ts                 fetch wrapper (base URL from import.meta.env.VITE_API_URL)
  lib/sse.ts                 useEventStream() hook with reconnect + ring buffer
  types/api.ts               AuditEvent, Finding, Decision, Policy, Budget… mirrors backend/docs/api-contract.md
  components/                DecisionBadge, RiskMeter, StatCard, RedactionDiff, EventDrawer, JsonView, EmptyState
  pages/
    Overview.tsx             posture KPIs, blocked/redacted %, top threats, p50/p95 latency per check
    LiveFeed.tsx             streaming table + drawer (original vs redacted, rule fired, score, timings)
    Approvals.tsx            pending tool calls → Approve / Deny
    Budgets.tsx              spend per agent and model vs limits
    Policy.tsx               mode + strictness switches, per-control toggles, raw YAML view
    Audit.tsx                filters + CSV / JSONL export
    AttackLab.tsx            (stretch) buttons that run demo scenarios
```

## Conventions

- **Types come from the API contract.** `src/types/api.ts` is hand-written to match [../backend/docs/api-contract.md](../backend/docs/api-contract.md). Update both together.
- **Decision colors are semantic and global**: allow = green, redact = amber, needs_approval = violet, block = red, monitor_only = outlined/dashed. Define them once as tokens and reuse them everywhere.
- The live feed keeps a **bounded ring buffer** (e.g. last 500 events) so the page never grows without limit during a long demo.
- Every page must handle three states: loading, empty (with a hint like "run `make demo`"), and backend offline.
- No business logic in the UI. Risk scores, decisions, and budgets are computed by the backend. The UI only displays them.
- Policy changes go through `PATCH /api/policy`. The backend writes `policy.yaml`, and the UI shows the new `policy_version` when the reload event arrives.
- Keep components small and colocated. No global state library. React Query + the SSE hook are enough.
- Dark theme first (it is a security console), and keep it readable on a projector: large numbers, high contrast.
- Remove the Vite starter content (`App.css` hero, `assets/hero.png`) when the shell is built.
