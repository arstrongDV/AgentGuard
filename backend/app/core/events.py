"""AuditEvent and SystemEvent payloads. Mirrors backend/docs/api-contract.md (and frontend/src/types/api.ts)."""

from typing import Any, Literal

from pydantic import BaseModel

from app.core.decision import CheckTiming, Decision, Finding

Channel = Literal["llm", "mcp"]
Direction = Literal["request", "response"]

ORIGINAL_TEXT_LIMIT = 8 * 1024
SUMMARY_LIMIT = 120


class ToolRef(BaseModel):
    server: str
    name: str
    arguments: dict[str, Any] | None = None


class Tokens(BaseModel):
    prompt: int
    completion: int


class AuditEvent(BaseModel):
    id: str
    ts: str
    trace_id: str
    task_id: str
    agent_id: str
    channel: Channel
    direction: Direction
    model: str | None = None
    tool: ToolRef | None = None
    decision: Decision
    monitor_only: bool = False
    would_have: Decision | None = None
    risk: float = 0.0
    findings: list[Finding] = []
    summary: str = ""
    original_text: str | None = None
    redacted_text: str | None = None
    timings: list[CheckTiming] = []
    total_ms: float = 0.0
    upstream_ms: float | None = None
    tokens: Tokens | None = None
    cost_usd: float | None = None
    cost_virtual: bool | None = None
    approval_id: str | None = None
    error: str | None = None
    policy_version: str

    def public(self) -> dict[str, Any]:
        """Shape used in lists and the live stream: no original/redacted bodies."""
        return self.model_dump(mode="json", exclude={"original_text", "redacted_text"})


def summarize(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SUMMARY_LIMIT else text[: SUMMARY_LIMIT - 1] + "…"


def truncate(text: str | None) -> str | None:
    if text is None or len(text) <= ORIGINAL_TEXT_LIMIT:
        return text
    return text[:ORIGINAL_TEXT_LIMIT] + "…[truncated]"
