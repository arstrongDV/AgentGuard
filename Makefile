# AgentGuard: common tasks. Run `make help`.
PY      := $(CURDIR)/backend/venv/bin/python
LLM     ?= mock            # mock | ollama   (make gateway LLM=ollama)
GATEWAY ?= http://localhost:8000

.DEFAULT_GOAL := help
.PHONY: help install models gateway mcp demo demo-all demo-live demo-llm seed test test-docker bench frontend up up-ollama down logs

help:  ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

install:  ## Create the backend venv and install backend (+ ML) and frontend dependencies
	test -d backend/venv || python3 -m venv backend/venv
	$(PY) -m pip install -q -r backend/requirements-dev.txt -r backend/requirements-ml.txt
	cd frontend && npm install

models:  ## Download the prompt-injection classifier (ONNX, ~740 MB) and print its SHA-256
	cd backend && $(PY) scripts/download_models.py

gateway:  ## Run the AgentGuard gateway on :8000 (LLM=mock by default, LLM=ollama for a real model)
	cd backend && LLM_PROVIDER=$(strip $(LLM)) $(PY) -m uvicorn app.main:app --reload --port 8000

mcp:  ## Run the mock MCP servers: CRM :9001, Email :9002, Bank :9003
	cd backend && $(PY) -m demo.mcp_servers

demo:  ## Stage demo (needs `make gateway` + `make mcp`): normal run + 3 attacks, unattended
	cd backend && $(PY) -m demo.agent --scenario demo --auto-approve deny --gateway $(GATEWAY)

demo-all:  ## Every scenario, unattended
	cd backend && $(PY) -m demo.agent --scenario all --auto-approve deny --gateway $(GATEWAY)

demo-live:  ## Injection against finance-bot; YOU approve/deny on the dashboard
	cd backend && $(PY) -m demo.agent --scenario injection_finance --gateway $(GATEWAY)

demo-llm:  ## Let a real model drive the injection scenario (needs `make gateway LLM=ollama`)
	cd backend && $(PY) -m demo.agent --scenario injection --mode llm --gateway $(GATEWAY)

seed:  ## Fill the dashboard: run every scenario against the running stack
	cd backend && $(PY) -m demo.agent --scenario all --auto-approve deny --gateway $(GATEWAY)

test:  ## Run the backend test suite (offline: no Ollama, no network)
	cd backend && $(PY) -m pytest

test-docker:  ## Run the test suite inside the backend image
	docker run --rm agentguard-backend pytest

bench:  ## Gateway overhead benchmark: latency per check, % of traffic that reached the ML tier
	cd backend && $(PY) scripts/bench.py

up:  ## docker compose up: gateway + mock MCP servers + dashboard (mock LLM, no downloads after build)
	docker compose up --build

up-ollama:  ## ...plus Ollama with qwen2.5:7b and granite3-guardian:2b (first run pulls ~6 GB)
	docker compose --profile ollama up --build

down:  ## Stop the stack
	docker compose --profile ollama down

logs:  ## Follow gateway logs
	docker compose logs -f gateway

frontend:  ## Run the dashboard dev server on :5173
	cd frontend && npm run dev
