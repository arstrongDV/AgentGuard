"""The demo scenarios as end-to-end tests: gateway + the REAL mock MCP servers (CRM, Email, Bank),
all in-process. If a policy or signature change breaks the stage demo, this fails first."""

import asyncio
from contextlib import AsyncExitStack

import httpx
import pytest

from demo.agent import AGENT_KEYS, PLACEHOLDER
from demo.mcp_servers import bank, email_service
from demo.mcp_servers.__main__ import SERVERS, build_app
from demo.scenarios import SCENARIOS, Scenario, Step
from app.config import BACKEND_DIR
from app.main import create_app
from tests.conftest import ADMIN

MODEL_READY = (BACKEND_DIR / "models" / "protectai__deberta-v3-base-prompt-injection-v2" / "onnx" / "model.onnx").exists()


async def hold_lifespans(apps, ready: asyncio.Event, stop: asyncio.Event) -> None:
    # The MCP servers' lifespans open anyio task groups, which must be entered and exited in the same
    # task. pytest-asyncio runs fixture setup and teardown in different tasks, so one task holds them.
    async with AsyncExitStack() as stack:
        for app in apps:
            await stack.enter_async_context(app.router.lifespan_context(app))
        ready.set()
        await stop.wait()


@pytest.fixture
async def real_mcp(svc):
    """Route the gateway's upstream traffic (localhost:9001-9003) to the real mock servers."""
    apps = {port: build_app(name, "127.0.0.1") for name, (_, port) in SERVERS.items()}
    ready, stop = asyncio.Event(), asyncio.Event()
    holder = asyncio.create_task(hold_lifespans(apps.values(), ready, stop))
    await ready.wait()
    original = svc.http
    svc.http = httpx.AsyncClient(mounts={f"http://localhost:{port}": httpx.ASGITransport(app=app) for port, app in apps.items()})
    email_service.OUTBOX.clear()
    bank.LEDGER.clear()
    yield
    await svc.http.aclose()
    svc.http = original
    stop.set()
    await holder


async def deny_pending_approvals(client: httpx.AsyncClient) -> None:
    """Plays the human reviewer: denies anything that asks for approval."""
    while True:
        for approval in (await client.get("/api/approvals", params={"status": "pending"})).json():
            await client.post(f"/api/approvals/{approval['id']}", json={"decision": "deny"}, headers=ADMIN)
        await asyncio.sleep(0.01)


async def run_step(client: httpx.AsyncClient, scenario: Scenario, step: Step, task: str, msg_id: int) -> str:
    key = AGENT_KEYS[scenario.agent]
    if step.kind == "chat":
        r = await client.post("/v1/chat/completions", headers={"Authorization": f"Bearer {key}", "X-AgentGuard-Task": task},
                              json={"model": "qwen2.5:7b", "messages": [{"role": "user", "content": step.prompt}]})
        return r.headers["x-agentguard-decision"]
    message = {"jsonrpc": "2.0", "id": msg_id, "method": "tools/call", "params": {"name": step.tool, "arguments": step.args}}
    reviewer = asyncio.create_task(deny_pending_approvals(client))
    try:
        r = await client.post(f"/mcp/{step.server}", json=message, headers={"X-Agent-Key": key, "X-AgentGuard-Task": task})
    finally:
        reviewer.cancel()
    result = r.json()["result"]
    text = "\n".join(block.get("text", "") for block in result["content"])
    if result.get("isError") and text.startswith("[AgentGuard]"):
        return "block"
    return "redact" if PLACEHOLDER.search(text) else "allow"


@pytest.mark.parametrize("name", list(SCENARIOS))
async def test_scenario(name, client, real_mcp):
    scenario = SCENARIOS[name]
    outcomes = [await run_step(client, scenario, step, f"test-{name}", i) for i, step in enumerate(scenario.script, 1)]
    assert outcomes == [step.expect for step in scenario.script]


async def test_nothing_leaves_the_bank(client, real_mcp):
    """After every attack scenario: no email went out, no money moved."""
    for name, scenario in SCENARIOS.items():
        for i, step in enumerate(scenario.script, 1):
            await run_step(client, scenario, step, f"leak-{name}", i)
    assert email_service.OUTBOX == []
    assert bank.LEDGER == []


async def test_approved_transfer_really_executes(client, real_mcp):
    """Approvals are not just a block in disguise: an approved call reaches the bank."""
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "transfer_money", "arguments": {"to_iban": "DE89370400440532013000", "amount": 250}}}
    pending = asyncio.create_task(client.post("/mcp/bank", json=call, headers={"X-Agent-Key": AGENT_KEYS["finance-bot"]}))
    for _ in range(200):
        approvals = (await client.get("/api/approvals", params={"status": "pending"})).json()
        if approvals:
            break
        await asyncio.sleep(0.01)
    await client.post(f"/api/approvals/{approvals[0]['id']}", json={"decision": "approve"}, headers=ADMIN)
    result = (await pending).json()["result"]
    assert result["isError"] is False
    assert [tx["amount"] for tx in bank.LEDGER] == [250]
    assert "[IBAN_1]" in result["content"][0]["text"]  # the receipt's IBAN is redacted on the way back


@pytest.fixture
async def ml_client(settings):
    """The gateway with the REAL injection classifier loaded (what `docker compose up` runs)."""
    app = create_app(settings.model_copy(update={"ml_enabled": True, "models_dir": BACKEND_DIR / "models"}))
    async with app.router.lifespan_context(app):
        svc = app.state.services
        for _ in range(1800):  # up to 3 min: loading takes ~3 s on a laptop, 20+ s on a busy Docker VM
            if svc.ml.classifier.status != "loading":
                break
            await asyncio.sleep(0.1)
        assert svc.ml.classifier.ready, svc.ml.classifier.detail
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client, svc


@pytest.mark.skipif(not MODEL_READY, reason="model not downloaded (make models)")
async def test_every_scenario_with_the_real_classifier(ml_client):
    """Regression: the classifier once flagged every benign CRM record (it scores JSON as an injection)."""
    client, svc = ml_client
    apps = {port: build_app(name, "127.0.0.1") for name, (_, port) in SERVERS.items()}
    ready, stop = asyncio.Event(), asyncio.Event()
    holder = asyncio.create_task(hold_lifespans(apps.values(), ready, stop))
    await ready.wait()
    svc.http = httpx.AsyncClient(mounts={f"http://localhost:{p}": httpx.ASGITransport(app=a) for p, a in apps.items()})
    try:
        for name, scenario in SCENARIOS.items():
            outcomes = [await run_step(client, scenario, step, f"ml-{name}", i) for i, step in enumerate(scenario.script, 1)]
            assert outcomes == [step.expect for step in scenario.script], name
        ran = (await client.get("/api/metrics")).json()["tier_reach"]["t2_pct"]
        assert ran > 0  # the classifier really ran (on tool results)
    finally:
        await svc.http.aclose()
        stop.set()
        await holder
