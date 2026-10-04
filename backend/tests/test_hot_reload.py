"""Hot reload: judges edit policy.yaml live and the gateway picks it up without a restart."""

import asyncio

import pytest

from app.config import Settings
from app.main import create_app


@pytest.fixture
async def watched_app(settings: Settings):
    app = create_app(settings.model_copy(update={"watch_policy": True}))
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.3)  # let the watcher start
        yield app


async def _wait_for(predicate, timeout: float = 5.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


async def test_edit_on_disk_is_applied(watched_app, settings):
    svc = watched_app.state.services
    queue = svc.bus.subscribe()
    before = svc.policy.current().version

    settings.policy_path.write_text(settings.policy_path.read_text().replace("mode: enforce", "mode: monitor"))

    assert await _wait_for(lambda: svc.policy.current().version != before)
    assert svc.policy.current().agents["support-bot"].mode == "monitor"
    kind, event = await asyncio.wait_for(queue.get(), 2)
    assert kind == "system" and event["type"] == "policy_reloaded"
    assert event["old_version"] == before and "mode enforce → monitor" in event["summary"]


async def test_invalid_edit_keeps_old_policy(watched_app, settings):
    svc = watched_app.state.services
    queue = svc.bus.subscribe()
    before = svc.policy.current().version

    settings.policy_path.write_text("mode: [this is not valid\n")

    kind, event = await asyncio.wait_for(queue.get(), 5)
    assert event["type"] == "policy_error"
    assert svc.policy.current().version == before


async def test_feed_edit_is_applied(watched_app, settings):
    svc = watched_app.state.services
    feed_path = svc.policy.feed_path
    count = svc.feed.count
    feed_path.write_text(feed_path.read_text().replace('"version": "2026-10-04"', '"version": "2026-10-05"'))
    assert await _wait_for(lambda: svc.feed.version == "2026-10-05")
    assert svc.feed.count == count


async def test_reconcile_catches_edits_the_watcher_misses(settings):
    """Docker bind mounts are polled by mtime+size; a same-second, same-size edit is invisible to them.
    The reconcile loop compares content hashes, so the policy still converges."""
    app = create_app(settings)  # watch_policy=False: no file events at all
    async with app.router.lifespan_context(app):
        svc = app.state.services
        stop = asyncio.Event()
        task = asyncio.create_task(svc.reconcile(stop, interval_s=0.05))
        before = svc.policy.current().version
        text = settings.policy_path.read_text()
        settings.policy_path.write_text(text.replace("mode: enforce ", "mode: monitor "))  # same size
        assert await _wait_for(lambda: svc.policy.current().version != before, timeout=2)
        assert svc.policy.current().agents["support-bot"].mode == "monitor"
        stop.set()
        await task
