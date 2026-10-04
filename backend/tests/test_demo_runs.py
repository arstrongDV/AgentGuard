"""Attack Lab: scenarios are listed and runs execute step by step (with a fake agent session: no network)."""

import asyncio

from demo.agent import ToolOutcome
from demo.scenarios import SCENARIOS
from tests.conftest import ADMIN


class FakeMessage:
    content = "Echo: ok"


class FakeSession:
    def __init__(self, gateway, agent, model, task_id, fail=False):
        self.fail = fail
        self.calls = []

    async def __aenter__(self):
        if self.fail:
            raise ExceptionGroup("unhandled errors in a TaskGroup", [ConnectionError("MCP servers down")])
        return self

    async def __aexit__(self, *exc):
        return None

    async def call_tool(self, server, name, args):
        self.calls.append(name)
        return ToolOutcome("block" if name == "transfer_money" else "allow", f"{server}.{name} ok")

    async def chat(self, messages, tools=None):
        return "allow", FakeMessage()


async def wait_done(client, run_id):
    for _ in range(200):
        run = (await client.get(f"/api/demo/runs/{run_id}")).json()
        if run["status"] != "running":
            return run
        await asyncio.sleep(0.01)
    raise AssertionError("run did not finish")


async def test_scenarios_are_listed(client):
    scenarios = (await client.get("/api/demo/scenarios")).json()
    assert [s["name"] for s in scenarios] == list(SCENARIOS)
    injection = next(s for s in scenarios if s["name"] == "injection")
    assert injection["agent"] == "support-bot" and injection["steps"][1]["label"].startswith("bank.transfer_money(")


async def test_run_executes_every_step(client, svc):
    svc.demo._session_factory = FakeSession
    r = await client.post("/api/demo/run", json={"scenario": "injection"}, headers=ADMIN)
    assert r.status_code == 200 and r.json()["task_id"].startswith("lab-injection-")
    run = await wait_done(client, r.json()["id"])
    assert run["status"] == "done"
    assert [s["decision"] for s in run["steps"]] == ["allow", "block"]
    assert (await client.get("/api/demo/runs")).json()[0]["id"] == run["id"]


async def test_run_failure_is_reported_not_raised(client, svc):
    svc.demo._session_factory = lambda *a: FakeSession(*a, fail=True)
    r = await client.post("/api/demo/run", json={"scenario": "benign"}, headers=ADMIN)
    run = await wait_done(client, r.json()["id"])
    assert run["status"] == "error" and "MCP servers down" in run["error"]


async def test_run_requires_admin_and_known_scenario(client):
    assert (await client.post("/api/demo/run", json={"scenario": "benign"})).status_code == 401
    assert (await client.post("/api/demo/run", json={"scenario": "nope"}, headers=ADMIN)).status_code == 404
