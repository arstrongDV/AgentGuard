# Frontend Implementation Plan

**Status (2026-10-04): steps 1–4 are built** (shell, data layer, Live Feed with drawer, Approvals), checked in a real
browser against the running stack (Playwright screenshots, clean console). Not built yet: fixtures / `VITE_USE_FIXTURES`
(the mock-LLM backend made them unnecessary so far), steps 5–9. Overview, Budgets, Policy and Audit routes show a placeholder.

The guiding idea: **the dashboard is the demo.** Judges spend most of the pitch looking at it, so it gets
real design effort, and it must look alive even before the backend is finished (fixtures).

## Dependencies to add

```bash
npm i react-router @tanstack/react-query recharts clsx   # react-icons already installed
npm i -D tailwindcss @tailwindcss/vite
```
(Optional: `@tanstack/react-virtual` if the feed table gets slow, and `diff` or a small custom span highlighter for redactions.)

## Steps

### Step 1: Shell (h 0–3)
- Remove the starter content. Add Tailwind via `@tailwindcss/vite` and the design tokens from [design-system.md](design-system.md).
- Layout: left sidebar (logo, nav: Overview, Live Feed, Approvals (with a badge), Budgets, Policy, Audit), top bar (status pills: Gateway ● / LLM ● / ML ● / policy `v3a9f…` / mode ENFORCE|MONITOR).
- `react-router` routes, one file per page under `src/pages/`.
- **Done when:** navigation works and the status bar reads `/health`, or shows "offline".

### Step 2: Types + data layer + fixtures (h 3–6)
- `src/types/api.ts` copied from the API contract.
- `src/lib/api.ts`, `src/lib/sse.ts`, `src/lib/queries.ts` (see [data-layer.md](data-layer.md)).
- `public/fixtures/` holds events, metrics, budgets, policy and approvals. `VITE_USE_FIXTURES=true` makes the SSE hook replay fixture events on a timer.
- **Done when:** with no backend running, the feed "streams" fixture events.

### Step 3: Live Feed (h 6–12) · most important page
- Streaming table + event drawer + redaction diff. See [pages-and-ux.md](pages-and-ux.md#2-live-feed).
- **Done when:** clicking an event shows the rule, score, timings, and the original vs redacted text.

### Step 4: Approvals (h 12–15)
- Pending cards with a countdown, Approve/Deny, and a toast when resolved. A sidebar badge counts pending approvals.
- **Done when:** the finance-bot transfer from the demo appears and can be denied live.

### Step 5: Overview (h 15–22)
- KPI cards, decisions-over-time area chart, top threat categories bar chart, latency per check (p50/p95) chart, "tier reach" stat.

### Step 6: Budgets + Policy (h 22–30)
- Budgets: a progress bar per agent for tokens and $, a per-model breakdown, a "virtual cost" tag.
- Policy: mode toggle, strictness segmented control per agent, per-control switches, read-only YAML viewer that flashes on reload, and an error banner when a `policy_error` arrives.

### Step 7: Audit export (h 30–33)
- Filter form (time range, agent, decision, category) + preview table + "Download CSV" / "Download JSONL" (a plain `<a href>` to the export endpoint).

### Step 8: Polish (h 33–40)
- Empty/loading/offline states everywhere, keyboard shortcuts (`/` focuses the feed search, `Esc` closes the drawer), favicon + title, a projector check at 1280×720.
- Stretch: Attack Lab page (buttons → `POST /api/demo/run`), and sound/flash on block (off by default).

### Step 9: Packaging
- `frontend/Dockerfile`: multi-stage, `npm ci && npm run build` → `nginx:alpine` serving `dist/`, with `VITE_API_URL` baked at build time (ARG).

## Definition of done (frontend)

- `npm run build` and `npm run lint` are clean.
- Every page works with the backend offline (an offline banner, not a white screen) and with fixtures.
- The 5-minute demo can be done entirely from the dashboard + one terminal.
- It looks good at 1280×720 on a projector and at 1920×1080.
