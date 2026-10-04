"""Service container: everything the request handlers share. One instance per app, on app.state.services."""

import asyncio
import logging
from pathlib import Path

import httpx
from watchfiles import awatch

from app.approvals import ApprovalQueue
from app.audit.bus import EventBus
from app.audit.store import AuditStore
from app.config import Settings
from app.core.events import AuditEvent
from app.core.ids import iso, utcnow
from app.core.pipeline import Runtime
from app.policy.feed import EMPTY_FEED, SignatureFeed, load_feed
from app.policy.store import PolicyError, PolicyStore, diff_summary
from app.providers import LLMProvider
from app.providers.mock import MockProvider
from app.providers.ollama import OllamaProvider
from app.state import State

log = logging.getLogger(__name__)


class Services:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.policy = PolicyStore(settings.policy_path)
        self.policy.load()  # fail fast: the gateway must not start without a valid policy
        self.feed: SignatureFeed = EMPTY_FEED
        self.state = State()
        self.bus = EventBus()
        self.audit = AuditStore(settings.data_dir)
        self.approvals = ApprovalQueue(self.bus)
        self.http = httpx.AsyncClient(timeout=settings.mcp_timeout_s)
        self.provider: LLMProvider = (
            MockProvider() if settings.llm_provider == "mock"
            else OllamaProvider(settings.ollama_url, self.http, settings.llm_timeout_s)
        )
        self.reload_feed(announce=False)
        self._rebuild_usage()

    def runtime(self) -> Runtime:
        return Runtime(snapshot=self.policy.current(), feed=self.feed, state=self.state)

    # --- audit ----------------------------------------------------------
    def emit(self, event: AuditEvent) -> None:
        self.audit.record(event)
        self.bus.publish("audit", event.public())
        if event.decision == "block":
            self.state.record_block(event.agent_id)

    def system_event(self, data: dict) -> None:
        self.bus.publish("system", {**data, "ts": iso(utcnow())})

    def _rebuild_usage(self) -> None:
        """Budgets survive restarts: replay today's spend from the audit log."""
        for e in self.audit.query(limit=1_000_000, since=self.state.day_start_iso(), ascending=True):
            if e.tokens and e.model:
                self.state.add_usage(e.agent_id, e.model, e.tokens.prompt + e.tokens.completion, e.cost_usd or 0.0, bool(e.cost_virtual))

    # --- hot reload -----------------------------------------------------
    def reload_policy(self) -> bool:
        """Re-read policy.yaml. Returns True when a new version was applied."""
        old_feed = self.policy.feed_path
        try:
            changed = self.policy.reload()
        except PolicyError as e:
            log.warning("policy reload rejected, keeping version %s: %s", self.policy.current().version, e.message)
            self.system_event({"type": "policy_error", "message": e.message, "line": e.line})
            return False
        if changed is None:
            return False
        old, new = changed
        log.info("policy reloaded %s -> %s", old.version, new.version)
        self.system_event({"type": "policy_reloaded", "old_version": old.version, "new_version": new.version,
                           "summary": diff_summary(old, new)})
        if self.policy.feed_path != old_feed:
            self.reload_feed()
        return True

    def reload_feed(self, announce: bool = True) -> None:
        path = self.policy.feed_path
        try:
            feed = load_feed(path)
        except Exception as e:  # keep the previous feed; a broken feed file must not disable the gateway
            log.error("signature feed %s not loaded: %s", path, e)
            if announce:
                self.system_event({"type": "policy_error", "message": f"signature feed rejected: {e}"})
            return
        changed = feed.version != self.feed.version or feed.count != self.feed.count
        self.feed = feed
        if announce and changed:
            self.system_event({"type": "feed_updated", "feed_version": feed.version, "count": feed.count})

    async def watch(self, stop: asyncio.Event) -> None:
        """Reload policy.yaml and the signature feed when they change on disk."""
        policy_path = self.settings.policy_path.resolve()
        dirs = {policy_path.parent, self.policy.feed_path.parent}
        async for changes in awatch(*dirs, stop_event=stop, debounce=200, recursive=False):
            changed = {Path(p).resolve() for _, p in changes}
            if policy_path in changed:
                self.reload_policy()
            if self.policy.feed_path in changed:
                self.reload_feed()

    async def aclose(self) -> None:
        await self.http.aclose()
        self.audit.close()
