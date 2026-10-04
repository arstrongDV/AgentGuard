"""MCP proxy: least privilege, argument checks, result scanning, approvals, loop detection."""

import asyncio

import pytest

from app.api.mcp import parse_sse_reply
from tests.conftest import ADMIN, FINANCE_KEY, SUPPORT_KEY

SUPPORT = {"X-Agent-Key": SUPPORT_KEY}
FINANCE = {"X-Agent-Key": FINANCE_KEY}


def rpc(method: str, params: dict | None = None, msg_id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}


def call(name: str, **arguments) -> dict:
    return rpc("tools/call", {"name": name, "arguments": arguments})


def tool_calls(calls: list[dict]) -> list[dict]:
    return [c for c in calls if c.get("method") == "tools/call"]


async def test_initialize_passthrough_with_session(client, fake_mcp):
    r = await client.post("/mcp/crm", json=rpc("initialize"), headers=SUPPORT)
    assert r.json()["result"]["serverInfo"]["name"] == "fake"
    assert r.headers["mcp-session-id"] == "sess-123"


async def test_notification_returns_202(client, fake_mcp):
    r = await client.post("/mcp/crm", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=SUPPORT)
    assert r.status_code == 202


async def test_tools_list_hides_forbidden_tools(client, fake_mcp):
    support = (await client.post("/mcp/bank", json=rpc("tools/list"), headers=SUPPORT)).json()
    assert {t["name"] for t in support["result"]["tools"]} == {"search_customers", "get_customer", "send_email"}
    finance = (await client.post("/mcp/bank", json=rpc("tools/list"), headers=FINANCE)).json()
    assert {t["name"] for t in finance["result"]["tools"]} == {"get_customer", "get_balance", "list_files", "transfer_money"}
    events = (await client.get("/api/events")).json()["items"]
    assert any(f["rule_id"] == "TOOLS-HIDDEN" for e in events for f in e["findings"])


async def test_allowed_call_forwarded_and_result_redacted(client, fake_mcp):
    r = await client.post("/mcp/crm", json=call("search_customers", query="Anna"), headers=SUPPORT)
    result = r.json()["result"]
    assert result["isError"] is False
    assert "[EMAIL_1]" in result["content"][0]["text"] and "anna.schmidt@example.com" not in result["content"][0]["text"]
    assert "[EMAIL_1]" in str(result["structuredContent"])  # structured output is scanned too
    assert r.headers["x-agentguard-decision"] == "redact"
    assert len(tool_calls(fake_mcp)) == 1


async def test_forbidden_tool_never_reaches_upstream(client, fake_mcp):
    r = await client.post("/mcp/bank", json=call("transfer_money", to_iban="DE89370400440532013000", amount=5000), headers=SUPPORT)
    result = r.json()["result"]
    assert result["isError"] is True and "TOOL-NOT-ALLOWED" in result["content"][0]["text"]
    assert tool_calls(fake_mcp) == []


async def test_attack_in_arguments_blocked(client, fake_mcp):
    r = await client.post("/mcp/crm", json=call("get_customer", id="../../etc/passwd"), headers=SUPPORT)
    assert "PATH-" in r.json()["result"]["content"][0]["text"]
    assert tool_calls(fake_mcp) == []


async def test_indirect_injection_in_tool_result_is_neutralised(client, fake_mcp):
    r = await client.post("/mcp/crm", json=call("search_customers", query="Mallory"), headers=SUPPORT)
    result = r.json()["result"]
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "Tool result blocked" in text and "transfer_money" not in text
    response_event = (await client.get("/api/events", params={"limit": 1})).json()["items"][0]
    assert response_event["direction"] == "response" and response_event["decision"] == "block"
    assert {"INJ-FAKE-SYSTEM", "INJ-IGNORE-PREV"} <= {f["rule_id"] for f in response_event["findings"]}


async def _wait_for_pending(client) -> dict:
    for _ in range(100):
        pending = (await client.get("/api/approvals", params={"status": "pending"})).json()
        if pending:
            return pending[0]
        await asyncio.sleep(0.01)
    raise AssertionError("no pending approval appeared")


@pytest.mark.parametrize("decision", ["approve", "deny"])
async def test_approval_flow(client, fake_mcp, decision):
    task = asyncio.create_task(
        client.post("/mcp/bank", json=call("transfer_money", to_iban="DE89370400440532013000", amount=500), headers=FINANCE)
    )
    approval = await _wait_for_pending(client)
    assert approval["tool"]["name"] == "transfer_money" and approval["agent_id"] == "finance-bot"

    r = await client.post(f"/api/approvals/{approval['id']}", json={"decision": decision}, headers=ADMIN)
    assert r.status_code == 200
    result = (await task).json()["result"]
    if decision == "approve":
        assert result["isError"] is False
        assert len(tool_calls(fake_mcp)) == 1
    else:
        assert result["isError"] is True and "APPROVAL-DENIED" in result["content"][0]["text"]
        assert tool_calls(fake_mcp) == []

    again = await client.post(f"/api/approvals/{approval['id']}", json={"decision": "approve"}, headers=ADMIN)
    assert again.status_code == 409
    history = (await client.get("/api/approvals")).json()
    assert history[0]["status"] == ("approved" if decision == "approve" else "denied")


async def test_approval_timeout_denies(client, fake_mcp):
    await client.patch("/api/policy", json={"agents": {"finance-bot": {"approval": {"timeout_s": 0.05}}}}, headers=ADMIN)
    r = await client.post("/mcp/bank", json=call("transfer_money", to_iban="DE89370400440532013000", amount=500), headers=FINANCE)
    assert "APPROVAL-TIMEOUT" in r.json()["result"]["content"][0]["text"]
    assert tool_calls(fake_mcp) == []


async def test_approval_requires_admin(client):
    r = await client.post("/api/approvals/whatever", json={"decision": "approve"})
    assert r.status_code == 401
    r = await client.post("/api/approvals/whatever", json={"decision": "approve"}, headers=ADMIN)
    assert r.status_code == 404


async def test_runaway_loop_is_stopped(client, fake_mcp):
    texts = []
    for _ in range(7):
        r = await client.post("/mcp/crm", json=call("get_customer", id="c-1"), headers=SUPPORT)
        texts.append(r.json()["result"]["content"][0]["text"])
    assert sum("LOOP-DETECTED" in t for t in texts) == 2  # medium strictness: 5 identical calls allowed
    assert len(tool_calls(fake_mcp)) == 5


async def test_task_tool_call_limit(client, fake_mcp):
    await client.patch("/api/policy", json={"agents": {"support-bot": {"budget": {"max_tool_calls_per_task": 2}}}}, headers=ADMIN)
    headers = {**SUPPORT, "X-AgentGuard-Task": "task-1"}
    results = [(await client.post("/mcp/crm", json=call("get_customer", id=f"c-{i}"), headers=headers)).json() for i in range(3)]
    assert "TASK-TOOL-CALLS" in results[2]["result"]["content"][0]["text"]


async def test_auth_and_unknown_server(client, fake_mcp):
    assert (await client.post("/mcp/crm", json=rpc("tools/list"))).status_code == 401
    r = await client.post("/mcp/nope", json=rpc("tools/list"), headers=SUPPORT)
    assert r.status_code == 404 and r.json()["error"]["code"] == -32004


async def test_upstream_down_returns_jsonrpc_error(client):
    # point the CRM at a port nobody listens on (independent of mock servers running on this machine)
    await client.patch("/api/policy", json={"mcp_servers": {"crm": {"url": "http://127.0.0.1:1/mcp"}}}, headers=ADMIN)
    r = await client.post("/mcp/crm", json=call("get_customer", id="c-1"), headers=SUPPORT)
    assert r.json()["error"]["code"] == -32002


def test_parse_sse_reply_picks_matching_response():
    body = (
        'event: message\ndata: {"jsonrpc":"2.0","method":"notifications/progress","params":{}}\n\n'
        'event: message\ndata: {"jsonrpc":"2.0","id":7,"result":{"ok":true}}\n\n'
    )
    assert parse_sse_reply(body, 7) == {"jsonrpc": "2.0", "id": 7, "result": {"ok": True}}
    assert parse_sse_reply(body, 8) is None
