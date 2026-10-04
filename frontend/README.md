# AgentGuard dashboard

React 19 + TypeScript + Vite security console for the AgentGuard gateway: Overview, Live Feed, Approvals,
Budgets, Policy, Audit export and Attack Lab.

```bash
npm install
npm run dev      # http://localhost:5173 (expects the gateway at VITE_API_URL, default http://localhost:8000)
npm run build    # type-check + production build
npm run lint     # oxlint
```

Docs: [docs/](docs/README.md) · conventions: [CLAUDE.md](CLAUDE.md) · API: [../backend/docs/api-contract.md](../backend/docs/api-contract.md).
In Docker the dashboard is built and served by nginx (`Dockerfile`, `nginx.conf`).
