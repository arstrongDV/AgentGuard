"""Budgets, rate limits and loop windows with an injected clock. Plus the SSE stream and metrics math."""

import asyncio

from app.api.events import sse_stream
from app.audit.bus import EventBus
from app.metrics import percentile
from app.state import State

DAY = 86_400


class Clock:
    def __init__(self, t: float = 1_790_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def test_usage_resets_at_utc_midnight():
    clock = Clock(1_790_035_200.0)  # 00:00 UTC
    state = State(clock)
    state.add_usage("a", "mock", 100, 0.01, True)
    assert state.usage("a").tokens == 100
    clock.t += DAY
    assert state.usage("a").tokens == 0


def test_rate_limit_window_slides():
    clock = Clock()
    state = State(clock)
    assert [state.hit_rate("a") for _ in range(3)] == [1, 2, 3]
    clock.t += 61
    assert state.hit_rate("a") == 1
    assert state.rpm("a") == 1


def test_loop_counts_previous_calls_in_window():
    clock = Clock()
    state = State(clock)
    assert [state.hit_loop("k", 60) for _ in range(3)] == [0, 1, 2]
    clock.t += 61
    assert state.hit_loop("k", 60) == 0


def test_task_counter_is_bounded():
    state = State(Clock())
    for i in range(10_050):
        state.hit_task("a", f"t{i}")
    assert state.hit_task("a", "t10049") == 2
    assert state.hit_task("a", "t0") == 1  # evicted, starts again


def test_percentile_nearest_rank():
    values = list(range(1, 101))
    assert percentile(values, 50) == 50
    assert percentile(values, 95) == 95
    assert percentile([], 95) == 0.0


async def test_sse_stream_delivers_events_and_pings():
    bus = EventBus()

    async def never_disconnected() -> bool:
        return False

    stream = sse_stream(bus, never_disconnected, ping_interval=0.05)
    assert await anext(stream) == "retry: 3000\n\n"
    pending = asyncio.ensure_future(anext(stream))
    await asyncio.sleep(0)
    bus.publish("audit", {"id": "e1"})
    assert await pending == 'event: audit\ndata: {"id":"e1"}\n\n'
    assert await anext(stream) == "event: ping\ndata: {}\n\n"
    await stream.aclose()
    assert bus.subscriber_count == 0
