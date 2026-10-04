"""MCP Proxy: JSON-RPC level proxy between agents and MCP servers (streamable HTTP transport).

tools/list -> filtered to the agent's allowlist (least privilege: forbidden tools are invisible)
tools/call -> pipeline on the call -> (approval) -> forward -> pipeline on the result
other      -> forwarded as is
See backend/docs/mcp-proxy.md.
"""

import copy
import json
import logging
from time import perf_counter
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from app.api.common import TASK_HEADER, build_event, decision_headers, get_services, identify_agent
from app.checks import CHECKS
from app.core.context import Redactor, RequestContext
from app.core.decision import Decision, Finding
from app.core.events import ToolRef, summarize
from app.core.ids import ulid
from app.core.pipeline import Runtime, block_message, run_pipeline
from app.core.text import apply_strings, collect_strings, tool_result_texts
from app.policy.effective import EffectiveAgent
from app.services import Services

log = logging.getLogger(__name__)
router = APIRouter(tags=["mcp proxy"])

PASSTHROUGH_HEADERS = ("mcp-session-id", "mcp-protocol-version", "last-event-id")


class UpstreamUnavailable(Exception):
    pass


def jsonrpc_error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def tool_error_result(msg_id: Any, text: str) -> dict[str, Any]:
    """A tool *result* with isError, not a protocol error: the agent keeps running and can explain the refusal."""
    return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": text}], "isError": True}}


@router.post("/mcp/{server}")
async def mcp_proxy(server: str, request: Request, svc: Services = Depends(get_services)):
    agent = identify_agent(svc, request.headers.get("x-agent-key"), "mcp")
    if agent is None:
        return JSONResponse(jsonrpc_error(None, -32001, "Invalid or missing X-Agent-Key"), status_code=401)
    upstream = svc.policy.current().policy.mcp_servers.get(server)
    if upstream is None:
        return JSONResponse(jsonrpc_error(None, -32004, f"Unknown MCP server '{server}'"), status_code=404)
    try:
        message = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(jsonrpc_error(None, -32700, "Parse error"), status_code=400)

    proxy = McpCall(svc, agent, server, upstream.url, request)
    if isinstance(message, list):  # JSON-RPC batch
        replies = [r for r in [await proxy.handle(m) for m in message] if r is not None]
        return JSONResponse(replies, headers=proxy.response_headers) if replies else Response(status_code=202)
    reply = await proxy.handle(message)
    if reply is None:
        return Response(status_code=202, headers=proxy.response_headers)
    return JSONResponse(reply, headers=proxy.response_headers)


class McpCall:
    def __init__(self, svc: Services, agent: EffectiveAgent, server: str, url: str, request: Request):
        self.svc, self.agent, self.server, self.url = svc, agent, server, url
        self.rt: Runtime = svc.runtime()
        self.trace_id = ulid()
        self.task_id = request.headers.get(TASK_HEADER) or self.trace_id
        self.forward_headers = {h: request.headers[h] for h in PASSTHROUGH_HEADERS if h in request.headers}
        self.response_headers: dict[str, str] = {}

    async def handle(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict):
            return jsonrpc_error(None, -32600, "Invalid Request")
        method = message.get("method")
        try:
            if method == "tools/list":
                return await self.tools_list(message)
            if method == "tools/call":
                return await self.tools_call(message)
            return await self.forward(message)
        except UpstreamUnavailable as e:
            return jsonrpc_error(message.get("id"), -32002, str(e))

    # --- upstream -------------------------------------------------------
    async def forward(self, message: dict[str, Any]) -> dict[str, Any] | None:
        headers = {"content-type": "application/json", "accept": "application/json, text/event-stream", **self.forward_headers}
        try:
            resp = await self.svc.http.post(self.url, json=message, headers=headers)
        except httpx.HTTPError as e:
            raise UpstreamUnavailable(f"MCP server '{self.server}' unavailable: {e.__class__.__name__}") from e
        if "mcp-session-id" in resp.headers:
            self.response_headers["mcp-session-id"] = resp.headers["mcp-session-id"]
        if resp.status_code in (202, 204) or not resp.content:
            return None
        if resp.headers.get("content-type", "").startswith("text/event-stream"):
            return parse_sse_reply(resp.text, message.get("id"))
        if resp.status_code >= 400 and "application/json" not in resp.headers.get("content-type", ""):
            raise UpstreamUnavailable(f"MCP server '{self.server}' returned HTTP {resp.status_code}")
        return resp.json()

    # --- tools/list -----------------------------------------------------
    async def tools_list(self, message: dict[str, Any]) -> dict[str, Any] | None:
        reply = await self.forward(message)
        tools = ((reply or {}).get("result") or {}).get("tools")
        if not isinstance(tools, list):
            return reply
        visible = set(self.agent.tools_allowed) | set(self.agent.tools_need_approval)
        kept = [t for t in tools if t.get("name") in visible]
        hidden = [t.get("name") for t in tools if t.get("name") not in visible]
        reply["result"]["tools"] = kept  # type: ignore[index]
        if hidden:
            ctx = self._ctx("mcp_call", [], ToolRef(server=self.server, name="tools/list"))
            self.svc.emit(build_event(
                ctx, None, self.rt.snapshot.version,
                summary=f"tools/list: {len(kept)} visible, {len(hidden)} hidden by policy",
                findings=[Finding(check="tool_acl", rule_id="TOOLS-HIDDEN", category="tool_acl", severity="low", score=0.0,
                                  message=f"hidden from {self.agent.id}: {', '.join(map(str, hidden))}")],
            ))
        return reply

    # --- tools/call -----------------------------------------------------
    async def tools_call(self, message: dict[str, Any]) -> dict[str, Any] | None:
        msg_id = message.get("id")
        params = message.get("params") or {}
        name = str(params.get("name", ""))
        container = {"arguments": copy.deepcopy(params.get("arguments") or {})}
        redactor = Redactor()
        version = self.rt.snapshot.version

        # 1. the call
        ctx = self._ctx("mcp_call", collect_strings(container["arguments"], ("arguments",)),
                        ToolRef(server=self.server, name=name, arguments=params.get("arguments") or {}), redactor)
        result = await run_pipeline(ctx, self.rt, CHECKS)
        apply_strings(container, ctx.texts)
        tool = ToolRef(server=self.server, name=name, arguments=container["arguments"])  # audit the redacted arguments
        self.response_headers.update(decision_headers(self.trace_id, result.decision, result.risk))

        approval_id = None
        if result.decision == Decision.needs_approval:
            approval = self.svc.approvals.create(self.agent.id, tool, result.risk, result.findings, self.agent.approval.timeout_s)
            approval_id = approval.id
        self.svc.emit(build_event(ctx, result, version, tool=tool, summary=f"{self.server}.{name}", approval_id=approval_id))

        if result.decision == Decision.block:
            return tool_error_result(msg_id, block_message(result, "Tool call"))
        if approval_id is not None:
            status = await self.svc.approvals.wait(approval_id, self.agent.approval.timeout_s, self.agent.approval.on_timeout)
            if status != "approved":
                rule = "APPROVAL-TIMEOUT" if status == "timeout" else "APPROVAL-DENIED"
                finding = Finding(check="approval", rule_id=rule, category="tool_acl", severity="high", score=1.0,
                                  message=f"{name} was {'not approved in time' if status == 'timeout' else 'denied by a reviewer'}")
                out = self._ctx("mcp_result", [], tool, redactor)
                self.svc.emit(build_event(out, None, version, decision=Decision.block, findings=[finding],
                                          summary=f"{self.server}.{name} → {status}", approval_id=approval_id))
                self.response_headers["x-agentguard-decision"] = Decision.block.value
                return tool_error_result(msg_id, f"[AgentGuard] Tool call blocked: {finding.message} ({rule})")

        # 2. forward with the (possibly redacted) arguments
        forwarded = {**message, "params": {**params, "arguments": container["arguments"]}}
        t0 = perf_counter()
        try:
            reply = await self.forward(forwarded)
        except UpstreamUnavailable as e:
            out = self._ctx("mcp_result", [], tool, redactor)
            self.svc.emit(build_event(out, None, version, summary=f"{self.server}.{name} → upstream error", error=str(e)))
            raise
        upstream_ms = round((perf_counter() - t0) * 1000, 1)
        if reply is None or "result" not in reply:
            error = (reply or {}).get("error")
            out = self._ctx("mcp_result", [], tool, redactor)
            self.svc.emit(build_event(out, None, version, summary=f"{self.server}.{name} → error", upstream_ms=upstream_ms,
                                      error=json.dumps(error) if error else "empty reply"))
            return reply

        # 3. the result (indirect injection, PII and secrets coming back from tools)
        tool_result = reply["result"]
        out = self._ctx("mcp_result", tool_result_texts(tool_result), tool, redactor)
        result_out = await run_pipeline(out, self.rt, CHECKS)
        if result_out.decision == Decision.block:
            reply = tool_error_result(msg_id, block_message(result_out, "Tool result"))
        else:
            apply_strings(tool_result, out.texts)
        self.svc.emit(build_event(out, result_out, version, upstream_ms=upstream_ms,
                                  summary=summarize(f"{self.server}.{name} → {result_out.redacted_text}")))
        if result_out.decision != Decision.allow:
            self.response_headers.update(decision_headers(self.trace_id, result_out.decision, max(result.risk, result_out.risk)))
        return reply

    def _ctx(self, stage, texts, tool: ToolRef, redactor: Redactor | None = None) -> RequestContext:
        return RequestContext(self.trace_id, self.task_id, self.agent, stage, texts, redactor or Redactor(), tool=tool)


def parse_sse_reply(body: str, msg_id: Any) -> dict[str, Any] | None:
    """Pick the JSON-RPC response for `msg_id` out of an SSE body (servers may also send notifications)."""
    found = None
    for block in body.split("\n\n"):
        data = "\n".join(line[5:].lstrip() for line in block.splitlines() if line.startswith("data:"))
        if not data:
            continue
        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(msg, dict) and msg.get("id") == msg_id and ("result" in msg or "error" in msg):
            found = msg
    return found
