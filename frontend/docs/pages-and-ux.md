# Pages and UX

Principles:
1. **Glanceable from 5 metres.** Big numbers, few colors, one clear story per page.
2. **Every red thing is explainable.** One click from any block/redact to the rule, the score, and the text.
3. **Alive.** New events slide in. Counters tick. Reloads flash. Judges should *see* the firewall working.

## Global shell

```
┌──────────┬──────────────────────────────────────────────────────────────────┐
│ ◆ Agent  │ Gateway ● online   LLM ● ollama   ML ● loaded   policy v3a9f  ENFORCE │
│   Guard  ├──────────────────────────────────────────────────────────────────┤
│          │                                                                  │
│ Overview │                         page content                             │
│ Live Feed│                                                                  │
│ Approvals│ (3)                                                              │
│ Budgets  │                                                                  │
│ Policy   │                                                                  │
│ Audit    │                                                                  │
└──────────┴──────────────────────────────────────────────────────────────────┘
```
- The mode pill is red/solid for ENFORCE and amber/dashed for MONITOR. Clicking it opens the Policy page.
- Toasts (bottom right) for: `policy_reloaded`, `policy_error`, `approval_requested`, and a block when you are not on the feed page.

## 1. Overview (posture)

```
┌ Requests ─┐┌ Blocked ──┐┌ Redacted ─┐┌ Overhead p95 ┐┌ Reached ML ┐
│   1,284   ││  7.2 %    ││  12.4 %   ││    38 ms     ││    9 %     │
└───────────┘└───────────┘└───────────┘└──────────────┘└────────────┘
┌ Decisions over time (stacked area: allow/redact/block) ──────────────────┐
└──────────────────────────────────────────────────────────────────────────┘
┌ Top threat categories (h-bar) ─────┐┌ Latency per check (p50/p95 bars) ─┐
│ prompt_injection ███████ 31        ││ signatures  ▏0.4 / 0.9 ms         │
│ pii              █████ 22          ││ pii         ▏0.6 / 1.2 ms         │
│ code_execution   ██ 8              ││ injection   ███ 18 / 35 ms        │
└────────────────────────────────────┘└ judge       ████████ 640/1200 ms ┘
```
- Time window selector: 15 m / 1 h / 24 h.
- **Wow:** the latency chart is grouped by tier with a caption: "T0–T1 run on 100% of traffic; T2 on 9%; T3 on 2%". That is the performance story in one picture.
- Clicking a category bar opens the Live Feed filtered to that category.

## 2. Live Feed

```
┌ filters: [agent ▾] [decision ▾] [channel ▾] [search…]      ⏸ Pause   ● live ┐
├──────┬─────────────┬──────┬─────────────────────────┬──────────┬──────┬─────┤
│ time │ agent       │ chan │ summary                  │ decision │ risk │ ms  │
├──────┼─────────────┼──────┼─────────────────────────┼──────────┼──────┼─────┤
│12:01 │ support-bot │ MCP  │ bank.transfer_money      │ ■ BLOCK  │ 0.97 │ 2.1 │
│12:01 │ support-bot │ MCP⇠ │ crm.search_customers     │ ■ REDACT │ 0.91 │ 21  │
│12:00 │ support-bot │ LLM  │ "Find customer Anna…"    │ ■ ALLOW  │ 0.02 │ 1.3 │
└──────┴─────────────┴──────┴─────────────────────────┴──────────┴──────┴─────┘
```
- New rows animate in (a short highlight in the decision color). The **Pause** button freezes the view during explanation, and a "N new" pill resumes it.
- Rows of the same `trace_id` get a thin left connector line, so a whole agent task reads as one story.
- `MCP⇠` = a tool result (response direction). `LLM⇢` = a completion.

**Event drawer (right side, 40% width):**
- Header: decision badge, agent, tool/model, risk meter, policy version, monitor-only badge ("would have blocked").
- **Findings list**: rule_id (mono), category chip, severity, score, message.
- **Redaction diff**: original and redacted text side by side; redacted spans are highlighted and the placeholders are shown as chips (`EMAIL_1`). A toggle switches to "inline" mode for long texts.
- **Pipeline timeline**: a horizontal waterfall of the checks with ms and the tier, with skipped checks greyed out showing the reason ("gated: risk 0.04 < 0.3"). **This is the best explanation of "hybrid detection" we have.**
- Tool calls: arguments shown as JSON with the offending value highlighted.
- Raw JSON (collapsible) + "Copy trace id".

## 3. Approvals

- Cards, not a table: agent, tool, arguments (pretty), risk + findings, and a **countdown ring** until auto-deny.
- Big **Approve** (neutral) and **Deny** (red) buttons, with an optional note.
- History below: resolved approvals with who/when/decision.
- Sidebar badge + toast + optional browser notification when a new approval arrives.

## 4. Budgets

- One card per agent: tokens/day and $/day progress bars (green → amber at 80% → red at 100%), "resets in 7h 12m".
- `virtual` tag with a tooltip: "Local model: priced with a virtual cost table to show cloud-equivalent spend."
- Per-model stacked bar, rate limit gauge (rpm), and "blocked today" count with a link to the feed filtered by `budget`/`loop`.

## 5. Policy

- Top: the **Mode** switch (Monitor ↔ Enforce) with a one-line explanation of each.
- Per agent: a **strictness** segmented control (Low / Medium / High), the tools allowed (chips), the tools needing approval (violet chips), and budget numbers.
- Controls: a switch + key parameters per control (PII entities, injection threshold slider, judge on/off).
- Right column: a read-only **YAML viewer** of `policy.yaml`. When a `policy_reloaded` event arrives, it flashes and shows "Reloaded v3a9f → v7c21 · just now".
- All changes go through `PATCH /api/policy`. The UI shows a spinner until the reload event confirms the change (the real round trip, not an optimistic update), so judges see that the file is the source of truth.

## 6. Audit

- Filters: date range, agent, decision, category, channel.
- A preview table (the same row component as the feed), with counts.
- Buttons: **Download CSV**, **Download JSONL**, and a "copy API URL" for SIEM people.

## 7. Attack Lab (stretch)

Buttons for each scenario ("Indirect injection", "PII leak", "Runaway loop", "SSRF in tool args"). Clicking one runs it via
`POST /api/demo/run` and auto-navigates to the Live Feed filtered to that trace. A judge can reproduce every attack without a terminal.
