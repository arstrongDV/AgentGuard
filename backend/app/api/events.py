import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.audit.bus import EventBus
from app.api.common import get_services
from app.services import Services

router = APIRouter(prefix="/api/events", tags=["events"])

PING_INTERVAL_S = 15.0


@router.get("")
def list_events(
    svc: Services = Depends(get_services),
    limit: int = Query(100, ge=1, le=1000),
    before: str | None = None,
    agent: str | None = None,
    decision: str | None = None,
    category: str | None = None,
):
    """Newest first. Page with `before=<next_before>` (an event id; ids sort by time)."""
    items = svc.audit.query(limit=limit, before_id=before, agent=agent, decision=decision, category=category)
    return {"items": [e.public() for e in items], "next_before": items[-1].id if len(items) == limit else None}


@router.get("/stream")
async def stream_events(request: Request, svc: Services = Depends(get_services)):
    async def disconnected() -> bool:
        return await request.is_disconnected()

    return StreamingResponse(
        sse_stream(svc.bus, disconnected),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )


@router.get("/{event_id}")
def get_event(event_id: str, svc: Services = Depends(get_services)):
    event = svc.audit.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    return event.model_dump(mode="json")


def sse_format(kind: str, data: dict) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


async def sse_stream(bus: EventBus, disconnected, ping_interval: float = PING_INTERVAL_S) -> AsyncIterator[str]:
    """`audit` and `system` events as they happen, plus a `ping` so clients can detect dead connections."""
    queue = bus.subscribe()
    try:
        yield "retry: 3000\n\n"
        while not await disconnected():
            try:
                kind, data = await asyncio.wait_for(queue.get(), ping_interval)
            except TimeoutError:
                yield sse_format("ping", {})
                continue
            yield sse_format(kind, data)
    finally:
        bus.unsubscribe(queue)
