"""Find the strings to scan inside OpenAI / MCP payloads, and write redacted strings back."""

from typing import Any

from app.core.context import Key, TextItem


def collect_strings(obj: Any, keys: tuple[Key, ...] = ()) -> list[TextItem]:
    """Every string leaf of a JSON-like value."""
    if isinstance(obj, str):
        return [TextItem(keys, obj)] if obj else []
    if isinstance(obj, dict):
        return [item for k, v in obj.items() for item in collect_strings(v, (*keys, k))]
    if isinstance(obj, list):
        return [item for i, v in enumerate(obj) for item in collect_strings(v, (*keys, i))]
    return []


def apply_strings(root: Any, items: list[TextItem]) -> None:
    """Write (possibly redacted) values back into `root` at their key paths."""
    for item in items:
        target = root
        for k in item.keys[:-1]:
            target = target[k]
        target[item.keys[-1]] = item.value


def chat_request_texts(body: dict[str, Any]) -> list[TextItem]:
    """messages[*].content, as a string or as a list of {type: text, text} parts."""
    items: list[TextItem] = []
    for i, message in enumerate(body.get("messages") or []):
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            items += collect_strings(content, ("messages", i, "content"))
        elif isinstance(content, list):
            for j, part in enumerate(content):
                if isinstance(part, dict) and part.get("type") == "text":
                    items += collect_strings(part.get("text"), ("messages", i, "content", j, "text"))
    return items


def chat_response_texts(body: dict[str, Any]) -> list[TextItem]:
    """choices[*].message.content and the arguments of proposed tool calls."""
    items: list[TextItem] = []
    for i, choice in enumerate(body.get("choices") or []):
        message = choice.get("message") or {}
        items += collect_strings(message.get("content"), ("choices", i, "message", "content"))
        for j, call in enumerate(message.get("tool_calls") or []):
            args = (call.get("function") or {}).get("arguments")
            items += collect_strings(args, ("choices", i, "message", "tool_calls", j, "function", "arguments"))
    return items


def tool_result_texts(result: dict[str, Any]) -> list[TextItem]:
    """MCP tools/call result: text content blocks and structuredContent string leaves."""
    items: list[TextItem] = []
    for i, block in enumerate(result.get("content") or []):
        if isinstance(block, dict) and block.get("type") == "text":
            items += collect_strings(block.get("text"), ("content", i, "text"))
    if "structuredContent" in result:
        items += collect_strings(result["structuredContent"], ("structuredContent",))
    return items


def joined(items: list[TextItem]) -> str:
    return "\n".join(item.value for item in items)
