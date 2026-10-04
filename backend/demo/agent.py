"""Demo agent: a plain tool-calling agent that talks to AgentGuard instead of directly to its LLM and tools.

The whole integration is two lines:
    OpenAI(base_url=f"{GATEWAY}/v1", api_key=AGENT_KEY)              # LLM traffic
    streamable_http_client(f"{GATEWAY}/mcp/<server>", X-Agent-Key)    # tool traffic

    python -m demo.agent --list
    python -m demo.agent --scenario injection                 # scripted (deterministic, default)
    python -m demo.agent --scenario injection --mode llm      # a real model decides (needs Ollama)
    python -m demo.agent --scenario demo --auto-approve deny  # the full stage demo, unattended
"""

import argparse
import asyncio
import json
import os
import re
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

import httpx
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
from openai import APIConnectionError, APIStatusError, AsyncOpenAI

from demo.scenarios import DEMO_ORDER, FINANCE_SYSTEM, SCENARIOS, SUPPORT_SYSTEM, Scenario, Step

AGENT_KEYS = {"support-bot": "ag-support-demo-key", "finance-bot": "ag-finance-demo-key"}
SERVERS = ["crm", "email", "bank"]
PLACEHOLDER = re.compile(r"\[(?:[A-Z]+_)+\d+\]|\[REMOVED_LINK\]")

# --- terminal output ---------------------------------------------------------

COLOR = sys.stdout.isatty() and not os.getenv("NO_COLOR")
STYLE = {"allow": "32", "redact": "33", "block": "31", "needs_approval": "35", "dim": "2", "bold": "1", "cyan": "36"}
BADGE = {"allow": "✓ ALLOW", "redact": "✎ REDACT", "block": "⛔ BLOCK", "needs_approval": "⏳ APPROVAL"}


def paint(text: str, style: str) -> str:
    return f"\033[{STYLE[style]}m{text}\033[0m" if COLOR else text


def show(decision: str, text: str) -> None:
    print(f"     {paint(BADGE.get(decision, decision).ljust(10), decision if decision in STYLE else 'dim')} {shorten(text)}")


def shorten(text: str, limit: int = 160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# --- gateway client ----------------------------------------------------------


@dataclass
class ToolOutcome:
    decision: str
    text: str


class AgentSession:
    """One agent identity, one task id, MCP sessions to every server through the AgentGuard proxy."""

    def __init__(self, gateway: str, agent: str, model: str, task_id: str):
        self.gateway, self.agent, self.model, self.task_id = gateway.rstrip("/"), agent, model, task_id
        key = AGENT_KEYS[agent]
        self.headers = {"X-Agent-Key": key, "X-AgentGuard-Task": task_id}
        self.llm = AsyncOpenAI(base_url=f"{self.gateway}/v1", api_key=key, default_headers={"X-AgentGuard-Task": task_id})
        self.sessions: dict[str, ClientSession] = {}
        self.visible_tools: dict[str, tuple[str, Any]] = {}  # name -> (server, mcp Tool)
        self._stack = AsyncExitStack()

    async def __aenter__(self) -> "AgentSession":
        # Approvals can hold a call open for a minute: allow long reads.
        http = await self._stack.enter_async_context(
            create_mcp_http_client(headers=self.headers, timeout=httpx2.Timeout(30, read=180))
        )
        for server in SERVERS:
            read, write = await self._stack.enter_async_context(streamable_http_client(f"{self.gateway}/mcp/{server}", http_client=http))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self.sessions[server] = session
            for t in (await session.list_tools()).tools:  # already filtered by AgentGuard
                self.visible_tools[t.name] = (server, t)
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._stack.aclose()

    async def call_tool(self, server: str, name: str, args: dict[str, Any]) -> ToolOutcome:
        result = await self.sessions[server].call_tool(name, args)
        text = "\n".join(getattr(block, "text", "") for block in result.content)
        if result.is_error and text.startswith("[AgentGuard]"):
            return ToolOutcome("block", text)
        return ToolOutcome("redact" if PLACEHOLDER.search(text) else "allow", text)

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> tuple[str, Any]:
        raw = await self.llm.chat.completions.with_raw_response.create(
            model=self.model, messages=messages, **({"tools": tools} if tools else {})
        )
        return raw.headers.get("x-agentguard-decision", "allow"), raw.parse().choices[0].message

    def openai_tools(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {"name": name, "description": t.description or "", "parameters": t.input_schema}}
                for name, (_, t) in self.visible_tools.items()]


# --- approvals -----------------------------------------------------------------


async def watch_approvals(gateway: str, agent: str, auto: str | None, admin_token: str) -> None:
    """While a tool call is pending, tell the presenter how to resolve it (or resolve it automatically)."""
    announced: set[str] = set()
    async with httpx.AsyncClient(base_url=gateway, timeout=5) as client:
        while True:
            await asyncio.sleep(0.4)
            try:
                pending = (await client.get("/api/approvals", params={"status": "pending"})).json()
            except httpx.HTTPError:
                continue
            for approval in pending:
                if approval["agent_id"] != agent or approval["id"] in announced:
                    continue
                announced.add(approval["id"])
                show("needs_approval", f"{approval['tool']['name']} is waiting for a human (id {approval['id']})")
                if auto:
                    await asyncio.sleep(1.5)  # long enough to see it in the dashboard
                    await client.post(f"/api/approvals/{approval['id']}", json={"decision": auto, "note": "demo auto-resolve"},
                                      headers={"Authorization": f"Bearer {admin_token}"})
                    print(paint(f"     → auto-{auto}d by the demo script", "dim"))
                else:
                    print(paint("     → Approve or deny it on the dashboard's Approvals page, or:", "dim"))
                    print(paint(f"       curl -X POST {gateway}/api/approvals/{approval['id']} -H 'Authorization: Bearer {admin_token}' "
                                "-H 'content-type: application/json' -d '{\"decision\":\"deny\"}'", "dim"))


async def with_approval_watch(coro, args: argparse.Namespace, agent: str):
    watcher = asyncio.create_task(watch_approvals(args.gateway, agent, args.auto_approve, args.admin_token))
    try:
        return await coro
    finally:
        watcher.cancel()


# --- runners ------------------------------------------------------------------


def system_prompt(agent: str) -> str:
    return FINANCE_SYSTEM if agent == "finance-bot" else SUPPORT_SYSTEM


async def run_scripted(session: AgentSession, scenario: Scenario, args: argparse.Namespace) -> None:
    for i, step in enumerate(scenario.script, 1):
        await run_step(session, step, i, args)


async def run_step(session: AgentSession, step: Step, i: int, args: argparse.Namespace) -> None:
    if step.note:
        print(paint(f"  {i}. {step.note}", "dim"))
    if step.kind == "tool":
        label = f"{step.server}.{step.tool}({json.dumps(step.args, ensure_ascii=False)})"
        print(f"     {paint('tool', 'cyan')} {shorten(label, 140)}")
        outcome = await with_approval_watch(session.call_tool(step.server, step.tool, step.args), args, session.agent)
        show(outcome.decision, outcome.text)
    else:
        print(f"     {paint('llm ', 'cyan')} {shorten(step.prompt, 140)}")
        messages = [{"role": "system", "content": system_prompt(session.agent)}, {"role": "user", "content": step.prompt}]
        decision, message = await session.chat(messages)
        show(decision, message.content or "")


async def run_llm(session: AgentSession, scenario: Scenario, args: argparse.Namespace) -> None:
    """A minimal ReAct-style loop: the model picks tools, AgentGuard checks every hop."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt(session.agent)},
                                      {"role": "user", "content": scenario.prompt}]
    print(f"     {paint('user', 'cyan')} {scenario.prompt}")
    for _ in range(args.max_steps):
        decision, message = await session.chat(messages, session.openai_tools())
        if not message.tool_calls:
            show(decision, message.content or "")
            return
        messages.append({"role": "assistant", "content": message.content or "",
                         "tool_calls": [c.model_dump() for c in message.tool_calls]})
        for call in message.tool_calls:
            name = call.function.name
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            print(f"     {paint('tool', 'cyan')} {shorten(f'{name}({json.dumps(arguments, ensure_ascii=False)})', 140)}")
            if name not in session.visible_tools:
                outcome = ToolOutcome("block", f"unknown tool {name}")
            else:
                server = session.visible_tools[name][0]
                outcome = await with_approval_watch(session.call_tool(server, name, arguments), args, session.agent)
            show(outcome.decision, outcome.text)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": outcome.text})
    print(paint(f"     stopped after {args.max_steps} model turns", "dim"))


async def run_scenario(scenario: Scenario, args: argparse.Namespace) -> None:
    task_id = f"demo-{scenario.name}-{os.urandom(3).hex()}"
    print()
    print(paint(f"▶ {scenario.title}", "bold") + paint(f"   agent={scenario.agent} mode={args.mode} task={task_id}", "dim"))
    async with AgentSession(args.gateway, scenario.agent, args.model, task_id) as session:
        visible = ", ".join(sorted(session.visible_tools)) or "none"
        print(paint(f"  tools visible to {scenario.agent}: {visible}", "dim"))
        if args.mode == "llm":
            await run_llm(session, scenario, args)
        else:
            await run_scripted(session, scenario, args)
    print(paint(f"  ⇒ {scenario.stops_it}", "dim"))


async def side_effects(args: argparse.Namespace) -> None:
    """What actually happened downstream: proof that nothing leaked."""
    async with httpx.AsyncClient(timeout=2) as client:
        for label, url in (("emails sent", "http://localhost:9002/outbox"), ("money transfers", "http://localhost:9003/ledger")):
            try:
                items = (await client.get(url)).json()
            except (httpx.HTTPError, ValueError):
                continue
            summary = "; ".join(f"{i.get('to') or i.get('to_iban')} {i.get('amount', '')}".strip() for i in items) or "none"
            print(paint(f"  downstream {label}: {len(items)} ({shorten(summary, 100)})", "dim"))


def first_leaf(e: BaseException) -> BaseException:
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return e


async def preflight(gateway: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            health = (await client.get(f"{gateway}/health")).json()
    except httpx.HTTPError:
        print(paint(f"AgentGuard gateway not reachable at {gateway}. Start it with `make gateway` (and `make mcp`).", "block"))
        return False
    print(paint(f"AgentGuard {gateway}  llm={health['llm']}  policy={health['policy_version']}  signatures={health['signatures']}", "dim"))
    return True


async def main_async(args: argparse.Namespace) -> int:
    if not await preflight(args.gateway):
        return 1
    names = DEMO_ORDER if args.scenario == "demo" else list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    try:
        for name in names:
            await run_scenario(SCENARIOS[name], args)
    except APIConnectionError:
        print(paint("Lost the connection to the gateway.", "block"))
        return 1
    except APIStatusError as e:
        print(paint(f"Gateway returned {e.status_code}: {e.message}", "block"))
        return 1
    except Exception as e:  # MCP transport errors arrive wrapped in (nested) exception groups
        root = first_leaf(e)
        if not isinstance(root, (httpx2.HTTPError, OSError)):
            raise
        print(paint(f"MCP connection failed ({root!r}). Are the mock servers running? `make mcp`", "block"))
        return 1
    print()
    await side_effects(args)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", default="demo", help="a scenario name, 'demo' (stage order) or 'all'")
    parser.add_argument("--mode", choices=["scripted", "llm"], default="scripted")
    parser.add_argument("--gateway", default=os.getenv("AGENTGUARD_URL", "http://localhost:8000"))
    parser.add_argument("--model", default=os.getenv("DEMO_MODEL", "qwen2.5:7b"))
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--auto-approve", choices=["approve", "deny"], help="resolve approvals automatically (unattended runs)")
    parser.add_argument("--admin-token", default=os.getenv("ADMIN_TOKEN", "dev-admin"))
    parser.add_argument("--list", action="store_true", help="list scenarios and exit")
    args = parser.parse_args()

    if args.list:
        for s in SCENARIOS.values():
            print(f"{s.name:<18} {s.agent:<12} {s.title}")
        return
    if args.scenario not in SCENARIOS and args.scenario not in ("demo", "all"):
        parser.error(f"unknown scenario {args.scenario!r}; see --list")
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
