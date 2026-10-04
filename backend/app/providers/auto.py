import logging
from typing import Any

from app.providers import UpstreamError
from app.providers.mock import MockProvider
from app.providers.ollama import OllamaProvider

log = logging.getLogger(__name__)


class AutoProvider:
    """Ollama when it is up and has the model; the mock LLM otherwise.

    The demo must never die because a model is still downloading. /health reports which one answers,
    and the dashboard shows it in the status bar, so nobody mistakes the mock for a real model."""

    name = "auto"

    def __init__(self, ollama: OllamaProvider, mock: MockProvider):
        self.ollama = ollama
        self.mock = mock

    async def chat(self, body: dict[str, Any]) -> dict[str, Any]:
        if await self.ollama.status() != "ollama":
            return await self.mock.chat(body)
        try:
            return await self.ollama.chat(body)
        except UpstreamError as e:
            if "404" in str(e):  # model not pulled yet
                log.warning("model %s not available in Ollama, answering with the mock LLM", body.get("model"))
                return await self.mock.chat(body)
            raise

    async def status(self) -> str:
        return "ollama" if await self.ollama.status() == "ollama" else "mock"
