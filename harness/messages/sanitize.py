"""Normalize message blocks before persistence or API calls."""

from __future__ import annotations

_BLOCK_FIELDS = (
    "type",
    "text",
    "thinking",
    "signature",
    "id",
    "name",
    "input",
    "tool_use_id",
    "content",
)


def block_to_dict(block) -> dict:
    """Convert SDK / dataclass / dict blocks to a plain dict."""
    if isinstance(block, dict):
        return dict(block)
    from dataclasses import asdict, is_dataclass
    from types import SimpleNamespace

    if is_dataclass(block):
        return asdict(block)
    if isinstance(block, SimpleNamespace):
        return {key: value for key, value in vars(block).items() if value is not None}
    if hasattr(block, "model_dump"):
        return block.model_dump()
    data: dict = {}
    for key in _BLOCK_FIELDS:
        value = getattr(block, key, None)
        if value is not None:
            data[key] = value
    if data.get("type"):
        return data
    block_type = getattr(block, "type", None)
    if block_type:
        data["type"] = block_type
    if not data and hasattr(block, "__dict__"):
        data = {
            key: value
            for key, value in vars(block).items()
            if not key.startswith("_") and value is not None
        }
    return data


def sanitize_content_blocks(blocks: list) -> list[dict]:
    """Drop blocks that would fail provider JSON validation."""
    cleaned: list[dict] = []
    for block in blocks:
        item = block_to_dict(block)
        block_type = item.get("type")
        if block_type == "thinking":
            if not item.get("thinking"):
                continue
        if block_type == "text" and not item.get("text"):
            continue
        if block_type == "tool_use":
            if not item.get("id") or not item.get("name"):
                continue
        if block_type == "tool_result":
            if not item.get("tool_use_id"):
                continue
        cleaned.append(item)
    return cleaned


def sanitize_messages_for_api(messages: list[dict]) -> list[dict]:
    """Ensure serialized messages are safe to send to Anthropic-compatible APIs."""
    sanitized: list[dict] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if isinstance(content, str):
            sanitized.append({"role": role, "content": content})
            continue
        if isinstance(content, list):
            blocks = sanitize_content_blocks(content)
            if not blocks:
                blocks = [{"type": "text", "text": "(empty)"}]
            sanitized.append({"role": role, "content": blocks})
            continue
        sanitized.append({"role": role, "content": str(content)})
    return sanitized
