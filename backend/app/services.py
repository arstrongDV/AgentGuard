"""Service container: everything the request handlers share. One instance per app, on app.state.services."""

import asyncio
import hashlib
import logging
from collections import Counter
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
from app.ml import MLRuntime
from app.ml.injection import InjectionClassifier
from app.ml.judge import LlmJudge
from app.policy.feed import EMPTY_FEED, SignatureFeed, load_feed, parse_feed
from app.policy.store import PolicyError, PolicyStore, diff_summary
from app.providers import LLMProvider
from app.providers.auto import AutoProvider
from app.providers.mock import MockProvider
from app.providers.ollama import OllamaProvider
from app.state import State

log = logging.getLogger(__name__)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


INJECTION_MODEL = "protectai/deberta-v3-base-prompt-injection-v2"


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
        self.http = httpx.AsyncClient(timeout=settings.mcp_timeout_s)  # MCP upstreams + feed URL
        self.llm_http = httpx.AsyncClient(timeout=settings.llm_timeout_s)  # Ollama (LLM + judge)
        self.provider: LLMProvider = self._make_provider()
        self._ollama_probe = OllamaProvider(settings.ollama_url, self.llm_http, settings.llm_timeout_s)  # cached reachability
        self.ml = MLRuntime(classifier=self._make_classifier(), judge=self._make_judge())
        self.counters: Counter[tuple[str, ...]] = Counter()  # Prometheus /metrics
        self.latency_sum: Counter[str] = Counter()
        self.latency_count: Counter[str] = Counter()
        self._feed_etag: str | None = None
        self._feed_file_hash: str | None = None
        self._feed_error: str | None = None
        self.reload_feed(announce=False)
        self._rebuild_usage()

    def _make_provider(self) -> LLMProvider:
        if self.settings.llm_provider == "mock":
            return MockProvider()
        ollama = OllamaProvider(self.settings.ollama_url, self.llm_http, self.settings.llm_timeout_s)
        return ollama if self.settings.llm_provider == "ollama" else AutoProvider(ollama, MockProvider())

    def _make_classifier(self) -> InjectionClassifier | None:
        if not self.settings.ml_enabled:
            return None
        pinned = self.policy.current().policy.supply_chain.pinned.get(INJECTION_MODEL)
        model_dir = self.settings.models_dir / INJECTION_MODEL.replace("/", "__")
        return InjectionClassifier(model_dir, pinned.sha256 if pinned else None, self.settings.ml_threads)

    async def judge_status(self) -> str:
        if self.ml.judge is None:
            return "disabled"
        if not self.ml.judge.available():
            return "unavailable"
        return "available" if await self._ollama_probe.status() == "ollama" else "unavailable"

    def _make_judge(self) -> LlmJudge | None:
        return LlmJudge(self.settings.ollama_url, self.llm_http) if self.settings.judge_enabled else None

    async def load_models(self) -> None:
        """Load the classifier off the event loop: the gateway serves (rules-only) while it loads."""
        if self.ml.classifier is not None:
            await asyncio.to_thread(self.ml.classifier.load)
            if not self.ml.classifier.ready:
                self.system_event({"type": "policy_error", "message": f"ML classifier unavailable: {self.ml.classifier.detail}"})

    def runtime(self) -> Runtime:
        return Runtime(snapshot=self.policy.current(), feed=self.feed, state=self.state, ml=self.ml)

    # --- audit ----------------------------------------------------------
    def emit(self, event: AuditEvent) -> None:
        self.audit.record(event)
        self.bus.publish("audit", event.public())
        if event.decision == "block":
            self.state.record_block(event.agent_id)
        self.counters[("events", event.channel, event.direction, event.decision.value, str(event.monitor_only).lower())] += 1
        for category in {f.category for f in event.findings if f.score > 0}:
            self.counters[("findings", category)] += 1
        for t in event.timings:
            if t.skipped_reason is None:
                self.latency_sum[t.check] += t.ms
                self.latency_count[t.check] += 1
            else:
                self.counters[("skipped", t.check)] += 1

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
        if self.policy.feed_path != old_feed and not self.feed_url:
            self.reload_feed()
        return True

    @property
    def feed_url(self) -> str | None:
        return self.policy.current().policy.controls.signatures.url

    def reload_feed(self, announce: bool = True) -> None:
        if self.feed_url and self.feed.count:
            return  # a URL feed is configured and loaded: the URL is the source of truth
        path = self.policy.feed_path
        try:
            self._feed_file_hash = _file_hash(path)
            feed = load_feed(path)
        except Exception as e:  # keep the previous feed; a broken feed file must not disable the gateway
            log.error("signature feed %s not loaded: %s", path, e)
            if announce:
                self.system_event({"type": "policy_error", "message": f"signature feed rejected: {e}"})
            return
        self._apply_feed(feed, announce)

    def _apply_feed(self, feed: SignatureFeed, announce: bool) -> None:
        changed = feed.version != self.feed.version or feed.count != self.feed.count
        self.feed = feed
        if announce and changed:
            self.system_event({"type": "feed_updated", "feed_version": feed.version, "count": feed.count})

    async def refresh_feed_from_url(self) -> bool:
        """One poll of controls.signatures.url (conditional GET). Returns True when a new feed was applied."""
        url = self.feed_url
        if not url:
            return False
        if not url.startswith(("https://", "http://")):
            self._report_feed_error(f"feed url must be http(s): {url}")
            return False
        headers = {"if-none-match": self._feed_etag} if self._feed_etag else {}
        try:
            resp = await self.http.get(url, headers=headers, timeout=10)
            if resp.status_code == 304:
                return False
            resp.raise_for_status()
            feed = parse_feed(resp.text)
        except Exception as e:  # unreachable, bad JSON, bad regex: keep the current feed
            self._report_feed_error(f"signature feed from {url} rejected: {e}")
            return False
        self._feed_etag = resp.headers.get("etag")
        self._feed_error = None
        changed = feed.version != self.feed.version or feed.count != self.feed.count
        self._apply_feed(feed, announce=True)
        return changed

    def _report_feed_error(self, message: str) -> None:
        if message != self._feed_error:  # report each distinct problem once, not every poll
            log.error(message)
            self.system_event({"type": "policy_error", "message": message})
        self._feed_error = message

    async def poll_feed(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.refresh_feed_from_url()
            refresh = max(5, self.policy.current().policy.controls.signatures.refresh_s)
            try:
                await asyncio.wait_for(stop.wait(), timeout=refresh)
            except TimeoutError:
                pass

    async def watch(self, stop: asyncio.Event) -> None:
        """Reload policy.yaml and the signature feed file when they change on disk."""
        policy_path = self.settings.policy_path.resolve()
        dirs = {policy_path.parent, self.policy.feed_path.parent}
        async for changes in awatch(*dirs, stop_event=stop, debounce=200, recursive=False):
            changed = {Path(p).resolve() for _, p in changes}
            if policy_path in changed:
                self.reload_policy()
            if self.policy.feed_path in changed and not self.feed_url:
                self.reload_feed()

    async def reconcile(self, stop: asyncio.Event, interval_s: float = 2.0) -> None:
        """Safety net under the file watcher. File events can be missed (Docker bind mounts poll mtime+size,
        so a same-second, same-size edit is invisible to them). Every couple of seconds, compare content
        hashes and reload if anything changed. Unchanged files cost one small read and a hash."""
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval_s)
            except TimeoutError:
                pass
            if stop.is_set():
                return
            try:
                self.reload_policy()
                if not self.feed_url and _file_hash(self.policy.feed_path) != self._feed_file_hash:
                    self.reload_feed()
            except OSError as e:  # file briefly missing during an editor's save
                log.debug("reconcile skipped: %s", e)

    async def aclose(self) -> None:
        await self.http.aclose()
        await self.llm_http.aclose()
        self.audit.close()
