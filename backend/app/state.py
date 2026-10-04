"""Mutable runtime state: budgets, rate limits, loop windows, per-task counters.

Everything mutable lives here, behind one small interface, so the request handlers stay stateless.
This implementation is in-memory (usage is rebuilt from the audit log on startup). A Redis-backed
implementation of the same methods is the path to running several gateway replicas.
"""

import time
from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Callable

MAX_TRACKED_TASKS = 10_000


@dataclass
class ModelUsage:
    tokens: int = 0
    usd: float = 0.0
    virtual: bool = False


@dataclass
class AgentUsage:
    tokens: int = 0
    usd: float = 0.0
    by_model: dict[str, ModelUsage] = field(default_factory=dict)


class State:
    def __init__(self, clock: Callable[[], float] = time.time):
        self.clock = clock
        self._usage: dict[tuple[str, str], AgentUsage] = defaultdict(AgentUsage)
        self._blocked: dict[tuple[str, str], int] = defaultdict(int)
        self._rate: dict[str, deque[float]] = defaultdict(deque)
        self._loops: dict[str, deque[float]] = defaultdict(deque)
        self._tasks: OrderedDict[tuple[str, str], int] = OrderedDict()

    # --- time -----------------------------------------------------------
    def day(self) -> str:
        return datetime.fromtimestamp(self.clock(), UTC).strftime("%Y-%m-%d")

    def day_start_iso(self) -> str:
        return self.day() + "T00:00:00.000Z"

    def seconds_until_reset(self) -> int:
        now = datetime.fromtimestamp(self.clock(), UTC)
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return int((midnight - now).total_seconds())

    # --- budgets --------------------------------------------------------
    def usage(self, agent_id: str) -> AgentUsage:
        return self._usage.get((self.day(), agent_id), AgentUsage())

    def add_usage(self, agent_id: str, model: str, tokens: int, usd: float, virtual: bool) -> None:
        usage = self._usage[(self.day(), agent_id)]
        usage.tokens += tokens
        usage.usd += usd
        per_model = usage.by_model.setdefault(model, ModelUsage(virtual=virtual))
        per_model.tokens += tokens
        per_model.usd += usd

    def record_block(self, agent_id: str) -> None:
        self._blocked[(self.day(), agent_id)] += 1

    def blocked_today(self, agent_id: str) -> int:
        return self._blocked.get((self.day(), agent_id), 0)

    # --- rate limit -----------------------------------------------------
    def _window(self, q: deque[float], window_s: float) -> deque[float]:
        cutoff = self.clock() - window_s
        while q and q[0] <= cutoff:
            q.popleft()
        return q

    def hit_rate(self, agent_id: str, window_s: float = 60) -> int:
        """Record one request; return how many requests happened in the window, including this one."""
        q = self._window(self._rate[agent_id], window_s)
        q.append(self.clock())
        return len(q)

    def rpm(self, agent_id: str) -> int:
        return len(self._window(self._rate[agent_id], 60))

    # --- loop detection -------------------------------------------------
    def hit_loop(self, key: str, window_s: float) -> int:
        """Record one call; return how many identical calls happened in the window BEFORE this one."""
        q = self._window(self._loops[key], window_s)
        previous = len(q)
        q.append(self.clock())
        return previous

    # --- per-task tool calls --------------------------------------------
    def hit_task(self, agent_id: str, task_id: str) -> int:
        key = (agent_id, task_id)
        self._tasks[key] = self._tasks.get(key, 0) + 1
        self._tasks.move_to_end(key)
        while len(self._tasks) > MAX_TRACKED_TASKS:
            self._tasks.popitem(last=False)
        return self._tasks[key]
