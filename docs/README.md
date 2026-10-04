# AgentGuard: Project Docs

Planning docs for the whole project. Backend and frontend have their own deeper docs.

| Doc | Read it when |
|---|---|
| [01-vision-and-pitch.md](01-vision-and-pitch.md) | You want to know *what* we build, *why*, and what makes it stand out |
| [02-architecture.md](02-architecture.md) | You need the big picture: components, request flow, deployment |
| [03-roadmap.md](03-roadmap.md) | You want to know what to build next, who owns what, and the cut lines |
| [04-demo-script.md](04-demo-script.md) | You are preparing the live demo or the pitch |
| [05-judging-map.md](05-judging-map.md) | You want to check that every scoring criterion has visible evidence |

Deeper docs:
- Backend: [../backend/docs/](../backend/docs/README.md): pipeline, checks, policy schema, MCP proxy, API contract, tests
- Frontend: [../frontend/docs/](../frontend/docs/README.md): pages, UX, design system, data layer

## One-paragraph summary

AgentGuard is a local, open-source **AI firewall for agents**. One FastAPI service exposes an
OpenAI-compatible LLM endpoint and an MCP proxy. Every prompt, completion, tool call and tool result
goes through a layered pipeline. Cheap deterministic checks always run (~1 ms). ML checks run only
when the risk is uncertain or the action is dangerous. Policy is a single YAML file that reloads on
save, budgets and loop detection stop runaway agents, and a React console shows every decision live
with the original and redacted text side by side. It runs with `docker compose up`, uses no paid
APIs, and ships 50+ YAML test cases.
