import time
from typing import Any

import httpx

from app.providers import UpstreamError

STATUS_CACHE_S = 10.0


class OllamaProvider:
    """Ollama already speaks the OpenAI API at /v1/chat/completions, so this is a thin forwarder."""

    name = "ollama"

    def __init__(self, base_url: str, http: httpx.AsyncClient, timeout_s: float):
        self.base_url = base_url.rstrip("/")
        self.http = http
        self.timeout_s = timeout_s
        self._status: tuple[float, str] = (0.0, "offline")

    async def chat(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = await self.http.post(f"{self.base_url}/v1/chat/completions", json={**body, "stream": False}, timeout=self.timeout_s)
        except httpx.HTTPError as e:
            raise UpstreamError(f"Ollama unreachable at {self.base_url}: {e.__class__.__name__}") from e
        if resp.status_code >= 400:
            raise UpstreamError(f"Ollama returned {resp.status_code}: {resp.text[:300]}", status=resp.status_code)
        return resp.json()

    async def status(self) -> str:
        checked_at, value = self._status
        if time.monotonic() - checked_at < STATUS_CACHE_S:
            return value
        try:
            ok = (await self.http.get(f"{self.base_url}/api/tags", timeout=1.0)).status_code == 200
        except httpx.HTTPError:
            ok = False
        value = "ollama" if ok else "offline"
        self._status = (time.monotonic(), value)
        return value
