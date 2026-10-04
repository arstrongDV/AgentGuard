# Data Layer

## `src/lib/api.ts`

```ts
const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
export async function api<T>(path: string, init?: RequestInit): Promise<T>   // throws ApiError {status, body}
export function adminHeaders(): HeadersInit   // Bearer token from localStorage (set on the Policy page; demo default prefilled)
```
- One wrapper, JSON in/out, a 10 s timeout via `AbortController`.
- With `VITE_USE_FIXTURES=true`, map GET paths to `/fixtures/<name>.json`.

## React Query (`src/lib/queries.ts`)

| Hook | Key | Refetch |
|---|---|---|
| `useHealth()` | `['health']` | every 5 s (drives the status bar + offline banner) |
| `useMetrics(window)` | `['metrics', window]` | every 5 s + invalidated by SSE (throttled to 1/s) |
| `useBudgets()` | `['budgets']` | every 5 s |
| `usePolicy()` | `['policy']` | invalidated on `policy_reloaded` |
| `useApprovals()` | `['approvals','pending']` | invalidated on `approval_*` events |
| `useEvent(id)` | `['event', id]` | once (full event with originals for the drawer) |
| `usePatchPolicy()` | mutation | no optimistic update: wait for the `policy_reloaded` SSE |
| `useResolveApproval()` | mutation | optimistic: remove the card, roll back on error |

## SSE hook (`src/lib/sse.ts`)

```ts
export function useEventStream(opts?: { max?: number; paused?: boolean }): {
  events: AuditEvent[]        // newest first, ring buffer (default max 500)
  status: 'connecting' | 'live' | 'offline'
  pendingWhilePaused: number
}
```
- One shared `EventSource` for the whole app (a module-level singleton + subscribers), so pages do not open multiple connections.
- Listen for `audit`, `system` and `ping`. `system` events are dispatched to a tiny emitter that toasts and invalidates queries.
- Reconnect: the browser `EventSource` auto-retries. Also mark the stream `offline` if no `ping` arrives for 30 s.
- On (re)connect, backfill with `GET /api/events?limit=100` and de-duplicate by `id`.
- While paused, buffer the new events and show the count. Resume merges them.

## Fixtures (`public/fixtures/`)

`events.json` (~40 events covering every decision, channel and category, including the three demo stories with shared trace ids),
`metrics.json`, `budgets.json`, `policy.json`, `approvals.json`.
The fixture SSE replays `events.json` at one event per 1.5 s in a loop, which is enough to build and demo the UI with no backend at all.

## Offline behaviour

- `useHealth` fails → a top banner reads "Gateway offline. Showing the last known data". Pages keep the cached data visible.
- Mutations are disabled while offline, and a tooltip explains why.
