from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from app.core.decision import CheckTiming, Finding
from app.core.events import ToolRef
from app.policy.effective import EffectiveAgent
from app.policy.feed import Stage

Key = str | int


@dataclass
class TextItem:
    """One scannable string inside a payload, addressed by its key path."""

    keys: tuple[Key, ...]
    value: str

    @property
    def path(self) -> str:
        out = ""
        for k in self.keys:
            out += f"[{k}]" if isinstance(k, int) else (f".{k}" if out else str(k))
        return out


class Redactor:
    """Stable placeholders for one trace: the same value always maps to the same placeholder,
    in both directions, so `anna@x.com` in the prompt and in the answer are both `[EMAIL_1]`."""

    def __init__(self) -> None:
        self._by_value: dict[tuple[str, str], str] = {}
        self._counters: Counter[str] = Counter()

    def placeholder(self, kind: str, value: str) -> str:
        key = (kind, value)
        if key not in self._by_value:
            self._counters[kind] += 1
            self._by_value[key] = f"[{kind}_{self._counters[kind]}]"
        return self._by_value[key]


@dataclass
class RequestContext:
    trace_id: str
    task_id: str
    agent: EffectiveAgent
    stage: Stage
    texts: list[TextItem]
    redactor: Redactor
    model: str | None = None
    tool: ToolRef | None = None
    findings: list[Finding] = field(default_factory=list)
    timings: list[CheckTiming] = field(default_factory=list)

    @property
    def inbound(self) -> bool:
        """True for traffic coming from the agent (prompt, tool call)."""
        return self.stage in ("llm_in", "mcp_call")

    @property
    def channel(self) -> str:
        return "llm" if self.stage.startswith("llm") else "mcp"

    @property
    def direction(self) -> str:
        return "request" if self.inbound else "response"

    @property
    def arguments(self) -> dict[str, Any]:
        return (self.tool.arguments or {}) if self.tool else {}
