"""In-process pub/sub that feeds SSE subscribers. Publishing never blocks: a slow subscriber loses
its oldest events instead of slowing the gateway down."""

import asyncio
from typing import Any

QUEUE_SIZE = 1000

Message = tuple[str, dict[str, Any]]  # (sse event name, payload)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Message]] = set()

    def subscribe(self) -> asyncio.Queue[Message]:
        q: asyncio.Queue[Message] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Message]) -> None:
        self._subscribers.discard(q)

    def publish(self, kind: str, data: dict[str, Any]) -> None:
        for q in self._subscribers:
            if q.full():
                q.get_nowait()
            q.put_nowait((kind, data))

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
