"""T3: LLM judge. Granite Guardian (Apache-2.0) via Ollama by default.

Granite Guardian takes the risk name as the system prompt ("jailbreak", "harm", ...) and answers Yes/No.
The judge is expensive, so the pipeline only asks it about uncertain or high-risk traffic, answers are
cached, and an unreachable Ollama switches the judge off for a while instead of slowing every request.
"""

import hashlib
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

CACHE_SIZE = 2048
CACHE_TTL_S = 600
BACKOFF_S = 30.0
MAX_CHARS = 6000


@dataclass(frozen=True)
class Verdict:
    risky: bool
    score: float
    cached: bool = False


class JudgeUnavailable(Exception):
    pass


class LlmJudge:
    def __init__(self, base_url: str, http: httpx.AsyncClient):
        self.base_url = base_url.rstrip("/")
        self.http = http
        self._cache: OrderedDict[str, tuple[float, Verdict]] = OrderedDict()
        self._down_until = 0.0
        self.detail = ""

    def available(self) -> bool:
        return time.monotonic() >= self._down_until

    async def ask(self, model: str, risk: str, text: str, timeout_s: float) -> Verdict:
        """Raises JudgeUnavailable (skip the check) or TimeoutError (apply the policy's on_timeout)."""
        key = hashlib.sha256(f"{model}|{risk}|{text}".encode()).hexdigest()
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
            self._cache.move_to_end(key)
            return Verdict(hit[1].risky, hit[1].score, cached=True)

        body = {
            "model": model,
            "messages": [{"role": "system", "content": risk}, {"role": "user", "content": text[:MAX_CHARS]}],
            "stream": False,
            "options": {"temperature": 0},
        }
        try:
            resp = await self.http.post(f"{self.base_url}/api/chat", json=body, timeout=timeout_s)
        except httpx.TimeoutException as e:
            raise TimeoutError(f"judge did not answer within {timeout_s:g}s") from e
        except httpx.HTTPError as e:
            self._back_off(f"Ollama unreachable: {e.__class__.__name__}")
            raise JudgeUnavailable(self.detail) from e
        if resp.status_code == 404:
            self._back_off(f"judge model {model} not pulled (ollama pull {model})")
            raise JudgeUnavailable(self.detail)
        if resp.status_code >= 400:
            raise JudgeUnavailable(f"judge error {resp.status_code}")

        answer = (resp.json().get("message") or {}).get("content", "").strip().lower()
        verdict = Verdict(risky=answer.startswith("yes"), score=0.95 if answer.startswith("yes") else 0.05)
        self._cache[key] = (time.monotonic(), verdict)
        while len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        return verdict

    def _back_off(self, reason: str) -> None:
        if self.available():
            log.warning("LLM judge disabled for %ss: %s", BACKOFF_S, reason)
        self.detail = reason
        self._down_until = time.monotonic() + BACKOFF_S
