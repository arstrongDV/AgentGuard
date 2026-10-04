# 01: Vision and Pitch

## The problem (say this in the first 20 seconds)

Companies are giving LLM agents real tools: CRMs, email, payments. Today most "AI security" only
looks at the **prompt**. But in agent systems the real damage happens elsewhere:

- a poisoned CRM note tells the agent to **transfer money** (indirect prompt injection),
- the model **leaks customer PII** in its answer,
- an agent gets stuck in a **loop** and burns tokens or calls the same API 500 times,
- a tool argument carries **`; rm -rf /`** or `http://169.254.169.254/` (classic attacks in new clothes).

Nobody is watching the **tool layer**, and nobody can show the security team *what the agent did*.

## The solution

**AgentGuard**: a drop-in firewall for AI agents.

- **Drop-in**: change one line (`base_url`) for the LLM. Point the MCP client at the proxy for tools. No SDK and no code changes.
- **Two control points, one brain**: the LLM Gateway and the MCP Proxy share one policy and one pipeline.
- **Least privilege for agents**: each agent sees only its allowed tools (forbidden tools are filtered out of `tools/list`), and dangerous tools need human approval.
- **Hybrid detection**: deterministic rules first (~1 ms), ML classifier and LLM judge only when needed. The latency per check is visible.
- **Budgets**: tokens/day, $/day (including a "virtual cost" for local models), rate limits, loop detection.
- **Live policy**: edit `policy.yaml` or flip a switch in the dashboard, and the change takes effect within a second without a restart.
- **Evidence**: every decision is an audit event, streamed live and exportable as CSV/JSONL.

## Why judges will like it (design principles)

1. **It works the first time.** `docker compose up` brings up the dashboard with data in it. A judge who clones the repo should see something within 3 minutes. This alone beats half of the field.
2. **The demo tells a story, not a feature list.** There are three attacks, each stopped by a different layer, and the audience watches it happen live in the console (see [04-demo-script.md](04-demo-script.md)).
3. **Defense in depth is visible.** In the injection attack, show that even if the classifier missed it, the tool ACL and the approval gate would still stop the transfer. Judges reward layered thinking.
4. **Numbers, not adjectives.** Show "deterministic checks: p50 0.8 ms; the semantic check runs on 12% of requests; p95 total overhead: 38 ms". Put the numbers on screen.
5. **Judges can play with it.** They can edit `policy.yaml` live, toggle `monitor`/`enforce`, and change strictness to `high`. A judge who touches the product remembers it.
6. **Honest engineering.** Licenses are checked, limitations are listed in the README, and the tests are data-driven. It reads like a product, not a hack.

## Differentiators vs. a "prompt filter" project

| Typical hackathon project | AgentGuard |
|---|---|
| Scans the user prompt only | Scans prompts, completions, **tool calls, tool results** |
| One regex list or one model | Tiered pipeline: rules → classifier → LLM judge, gated by risk |
| Static config | Hot-reloaded YAML + dashboard switches |
| Logs to console | Audit DB, SSE live feed, CSV/JSONL export, per-check latency |
| Allow/block | Allow / **redact** / block / **needs human approval**, plus monitor mode |
| No cost control | Token/$ budgets, rate limits, loop detection |

## Personas (who we say it is for)

- **Platform engineer**: wants to integrate it without rewriting agents. The pitch: "change `base_url`".
- **Security engineer**: wants visibility and evidence. The pitch: live feed, audit export, signatures feed.
- **Team lead / FinOps**: wants no surprise bills. The pitch: budgets per agent and per model.

## Tagline options

- "A firewall for what your agents *do*, not just what they say."
- "Least privilege for AI agents, in one line of config."
