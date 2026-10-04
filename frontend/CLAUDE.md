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

## Stack (+ = still to add)

- React 19, TypeScript 6 (strict, `verbatimModuleSyntax`, so use `import type`), Vite 8, oxlint
- `react-router` v8 for pages (`BrowserRouter`, nested routes under `components/Layout.tsx`)
- `@tanstack/react-query` for REST data (health, policy, approvals, event detail)
- native `EventSource` for the live feed (`/api/events/stream`), one shared connection in `lib/stream.ts`. No socket libraries.
- `tailwindcss` v4 via `@tailwindcss/vite`; tokens in `src/index.css` `@theme` (`bg surface surface-2 line fg muted accent` +
  decision colors `allow redact approval block`). The reset lives in `@layer base` so utilities always win.
- `clsx` for conditional classes
- + `recharts` for charts (Overview, Budgets)
- `react-icons` for icons: `react-icons/lu` (Lucide set) for UI icons, `react-icons/si` (Simple Icons) for brand logos

## Layout (built: shell, Live Feed, Approvals; the other pages are `ComingSoon` placeholders)

```
src/
  main.tsx, App.tsx          router + QueryClientProvider + layout shell
  lib/api.ts                 fetch wrapper (base URL from import.meta.env.VITE_API_URL)
  lib/stream.ts              useEventStream() + onSystemEvent(): shared EventSource, backfill, ring buffer, silence watchdog
  lib/queries.ts             React Query hooks; lib/toast.ts, lib/diff.ts (redaction alignment), lib/decision.ts (colors)
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
- Decision class strings live in `lib/decision.ts`, written out in full so Tailwind can find them. Never build class names dynamically.
- The selected event and the filters are URL params (`/feed?event=<id>&decision=block`), so any view can be linked to.
- Port 5173 may be taken by another project: Vite then uses 5174+, and the gateway's CORS accepts any localhost port.
