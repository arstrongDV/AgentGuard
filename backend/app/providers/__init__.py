from typing import Any, Protocol


class UpstreamError(Exception):
    """The LLM backend failed (unreachable, timeout, or error status)."""


class LLMProvider(Protocol):
    name: str

    async def chat(self, body: dict[str, Any]) -> dict[str, Any]:
        """OpenAI chat.completions request (non-streaming) -> OpenAI chat.completion response."""
        ...

    async def status(self) -> str:
        """'ollama' | 'mock' | 'offline'"""
        ...
