# Design System

Look and feel: **a calm security console**. Dark, dense but not cramped, color used only for meaning.
Think of a SOC tool, not a gaming UI: no neon gradients and no glassmorphism.

## Color tokens (Tailwind v4 `@theme` in `index.css`)

| Token | Use | Dark value (suggested) |
|---|---|---|
| `--bg` | app background | `#0b0f14` |
| `--surface` | cards, drawer | `#121821` |
| `--surface-2` | hover, table stripes | `#18202b` |
| `--border` | 1px dividers | `#243041` |
| `--text` / `--text-muted` | body / secondary | `#e6edf3` / `#8b98a9` |
| `--accent` | brand, links, focus ring | `#4c8dff` |
| `--allow` | allow | `#2fbf71` |
| `--redact` | redact | `#f0b429` |
| `--approval` | needs_approval | `#9b6dff` |
| `--block` | block | `#f0544f` |
| `--monitor` | monitor-only (dashed outline of the would-have color) | — |

Rules:
- **Decision colors appear only for decisions** (badges, chart series, row highlight, diff spans). Never use them for decoration.
- Severity is a separate scale (an icon plus text weight), so color is not overloaded.
- Contrast is ≥ 4.5:1 for text, and readable on a washed-out projector. Test at 1280×720 with brightness down.
- Provide a light theme only if there is time. Dark is the default.

## Typography

- UI: `Inter` (or the system UI font stack). Mono: `JetBrains Mono` for rule IDs, trace IDs, JSON, YAML, and ms values.
- Scale: KPI numbers 36–40 px semibold. Page title 20 px. Body 14 px. Table 13 px. Use tabular numbers (`font-variant-numeric: tabular-nums`) for all metrics.

## Core components (`src/components/`)

| Component | Notes |
|---|---|
| `DecisionBadge` | filled pill with icon (✓ allow, ✎ redact, ⏳ approval, ⛔ block). `monitorOnly` → dashed outline + "would block" |
| `RiskMeter` | a 0–1 bar with ticks at the policy thresholds (0.3 gate, 0.85 block) |
| `StatCard` | label, big number, delta vs previous window, optional sparkline |
| `EventRow` | used by both the Live Feed and the Audit preview |
| `EventDrawer` | findings, diff, pipeline timeline, raw JSON |
| `RedactionDiff` | renders text with spans highlighted, and placeholders as chips |
| `PipelineTimeline` | waterfall of checks per tier, with skipped checks greyed |
| `CountdownRing` | approvals |
| `JsonView` / `YamlView` | mono, collapsible, with highlighted paths |
| `StatusPill` | the top bar's health indicators |
| `EmptyState` / `OfflineBanner` | always offers a next action ("run `make demo`") |

## Charts (Recharts)

- Series colors = decision tokens. Grid lines `--border` at 40% opacity. No 3D and no pie charts (use horizontal bars for categories).
- Tooltips use the mono font for numbers and always include units (ms, tokens, $).
- Latency charts: p50 solid, p95 lighter with the same hue.

## Motion

- New feed row: a 600 ms background fade from the decision color at 20% to transparent.
- Policy reload: the YAML viewer border flashes accent once.
- Respect `prefers-reduced-motion`. No continuous animations except the "● live" dot.

## Voice and copy

- Plain, factual, and English only: "Blocked: tool `transfer_money` is not allowed for support-bot" rather than "Threat neutralised!".
- Always name the rule and the reason. Security people want specifics.
