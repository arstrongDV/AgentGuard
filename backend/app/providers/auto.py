import logging
from typing import Any

from app.providers import UpstreamError
from app.providers.mock import MockProvider
from app.providers.ollama import OllamaProvider

log = logging.getLogger(__name__)


class AutoProvider:
    """Ollama when it is up and can answer; the mock LLM otherwise.

    The demo must never die because a model is still downloading, does not fit in memory, or Ollama is
    restarting. /health reports which one answers (and why it fell back), and the dashboard shows it, so
    nobody mistakes the mock for a real model. Client mistakes (4xx other than 404) are not hidden."""

    name = "auto"

    def __init__(self, ollama: OllamaProvider, mock: MockProvider):
        self.ollama = ollama
        self.mock = mock
        self.last_fallback: str = ""

    async def chat(self, body: dict[str, Any]) -> dict[str, Any]:
        if await self.ollama.status() != "ollama":
            return await self.mock.chat(body)
        try:
            reply = await self.ollama.chat(body)
            self.last_fallback = ""
            return reply
        except UpstreamError as e:
            if e.status is not None and 400 <= e.status < 500 and e.status != 404:
                raise  # a bad request is the caller's problem: don't paper over it
            # 404: model not pulled yet · 5xx: e.g. not enough memory to load it · None: timeout / connection
            self.last_fallback = f"{body.get('model')}: {e}"
            log.warning("Ollama could not answer (%s); answering with the mock LLM", self.last_fallback)
            return await self.mock.chat(body)

    async def status(self) -> str:
        return "ollama" if await self.ollama.status() == "ollama" else "mock"
