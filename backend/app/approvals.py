"""Human-in-the-loop approvals for tools in `tools_need_approval`.

The MCP proxy holds the tool call open (awaiting a future) until someone approves or denies it in the
dashboard, or the timeout applies the policy's `on_timeout` decision.
"""

import asyncio
from collections import deque
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel

from app.audit.bus import EventBus
from app.core.decision import Finding
from app.core.events import ToolRef
from app.core.ids import iso, ulid, utcnow

Status = Literal["pending", "approved", "denied", "timeout"]
HISTORY_SIZE = 200


class Approval(BaseModel):
    id: str
    created_at: str
    expires_at: str
    agent_id: str
    tool: ToolRef
    risk: float
    findings: list[Finding]
    status: Status = "pending"
    note: str | None = None


class ApprovalQueue:
    def __init__(self, bus: EventBus):
        self.bus = bus
        self._pending: dict[str, tuple[Approval, asyncio.Future[str]]] = {}
        self._history: deque[Approval] = deque(maxlen=HISTORY_SIZE)

    def create(self, agent_id: str, tool: ToolRef, risk: float, findings: list[Finding], timeout_s: float) -> Approval:
        now = utcnow()
        approval = Approval(
            id=ulid(), created_at=iso(now), expires_at=iso(now + timedelta(seconds=timeout_s)),
            agent_id=agent_id, tool=tool, risk=risk, findings=findings,
        )
        self._pending[approval.id] = (approval, asyncio.get_running_loop().create_future())
        self.bus.publish("system", {"type": "approval_requested", "approval": approval.model_dump(mode="json")})
        return approval

    async def wait(self, approval_id: str, timeout_s: float, on_timeout: Literal["deny", "approve"]) -> Status:
        approval, future = self._pending[approval_id]
        try:
            decision = await asyncio.wait_for(asyncio.shield(future), timeout_s)
            status: Status = "approved" if decision == "approve" else "denied"
        except TimeoutError:
            status = "timeout"
            approval.note = f"auto-{on_timeout} after {timeout_s:g}s"
        self._finish(approval, status)
        # A timeout that the policy resolves as "approve" still lets the call through.
        return "approved" if status == "timeout" and on_timeout == "approve" else status

    def resolve(self, approval_id: str, decision: Literal["approve", "deny"], note: str | None = None) -> Approval:
        if approval_id not in self._pending:
            raise KeyError(approval_id)
        approval, future = self._pending[approval_id]
        approval.note = note
        if not future.done():
            future.set_result(decision)
        return approval

    def list(self, status: Status | None = None) -> list[Approval]:
        items = [a for a, _ in self._pending.values()] + list(reversed(self._history))
        return [a for a in items if status is None or a.status == status]

    def _finish(self, approval: Approval, status: Status) -> None:
        approval.status = status
        self._pending.pop(approval.id, None)
        self._history.append(approval)
        self.bus.publish("system", {"type": "approval_resolved", "approval_id": approval.id,
                                    "decision": {"approved": "approve", "denied": "deny"}.get(status, "timeout")})
