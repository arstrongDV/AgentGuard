"""Attack Lab: run a demo scenario from the dashboard.

The runner drives the same demo agent as `make demo` (demo/agent.py) against this gateway's own public
endpoints, so every step goes through the real LLM gateway and MCP proxy and shows up in the Live Feed.
Steps that need approval wait for a human on the Approvals page, exactly like a real agent would.
"""

import asyncio
import json
import logging
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel

from app.core.ids import iso, ulid, utcnow

log = logging.getLogger(__name__)

MAX_RUNS = 50


class StepResult(BaseModel):
    index: int
    kind: Literal["tool", "chat"]
    label: str
    note: str
    expect: str
    status: Literal["pending", "running", "done"] = "pending"
    decision: str | None = None
    text: str | None = None


class DemoRun(BaseModel):
    id: str
    scenario: str
    title: str
    agent: str
    task_id: str
    status: Literal["running", "done", "error"] = "running"
    started_at: str
    finished_at: str | None = None
    steps: list[StepResult]
    error: str | None = None


def step_label(step: Any) -> str:
    if step.kind == "tool":
        return f"{step.server}.{step.tool}({json.dumps(step.args, ensure_ascii=False)})"
    return step.prompt


class DemoRunner:
    def __init__(self, gateway_url: str, model: str, session_factory: Callable[..., Any] | None = None):
        self.gateway_url = gateway_url
        self.model = model
        self._session_factory = session_factory
        self._runs: OrderedDict[str, DemoRun] = OrderedDict()
        self._tasks: set[asyncio.Task] = set()

    # imported lazily: the demo package (openai + mcp clients) is only needed when someone clicks "Run"
    def _session(self, agent: str, task_id: str):
        if self._session_factory is not None:
            return self._session_factory(self.gateway_url, agent, self.model, task_id)
        from demo.agent import AgentSession

        return AgentSession(self.gateway_url, agent, self.model, task_id)

    def scenarios(self) -> list[dict[str, Any]]:
        from demo.scenarios import SCENARIOS

        return [
            {"name": s.name, "title": s.title, "agent": s.agent, "prompt": s.prompt, "stops_it": s.stops_it,
             "steps": [{"kind": st.kind, "label": step_label(st), "note": st.note, "expect": st.expect} for st in s.script]}
            for s in SCENARIOS.values()
        ]

    def start(self, name: str) -> DemoRun:
        from demo.scenarios import SCENARIOS

        scenario = SCENARIOS[name]  # KeyError -> 404
        run = DemoRun(
            id=ulid(), scenario=name, title=scenario.title, agent=scenario.agent, task_id=f"lab-{name}-{ulid()[-6:].lower()}",
            started_at=iso(utcnow()),
            steps=[StepResult(index=i, kind=st.kind, label=step_label(st), note=st.note, expect=st.expect)
                   for i, st in enumerate(scenario.script, 1)],
        )
        self._runs[run.id] = run
        while len(self._runs) > MAX_RUNS:
            self._runs.popitem(last=False)
        task = asyncio.create_task(self._execute(run, scenario))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run

    async def _execute(self, run: DemoRun, scenario: Any) -> None:
        try:
            async with self._session(run.agent, run.task_id) as session:
                for result, step in zip(run.steps, scenario.script):
                    result.status = "running"
                    if step.kind == "tool":
                        outcome = await session.call_tool(step.server, step.tool, step.args)
                        result.decision, result.text = outcome.decision, outcome.text
                    else:
                        system = "You are the support assistant of OurBank. Answer briefly."
                        decision, message = await session.chat([{"role": "system", "content": system},
                                                                {"role": "user", "content": step.prompt}])
                        result.decision, result.text = decision, message.content or ""
                    result.status = "done"
            run.status = "done"
        except Exception as e:  # MCP servers down, gateway URL wrong...: show it on the card, never crash
            root = e
            while isinstance(root, BaseExceptionGroup) and root.exceptions:
                root = root.exceptions[0]
            log.warning("demo run %s failed: %r", run.id, root)
            run.status, run.error = "error", f"{type(root).__name__}: {root}"
        finally:
            run.finished_at = iso(utcnow())

    def get(self, run_id: str) -> DemoRun | None:
        return self._runs.get(run_id)

    def list(self) -> list[DemoRun]:
        return list(reversed(self._runs.values()))

    async def aclose(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
