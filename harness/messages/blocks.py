"""Read message content blocks whether stored as dicts or objects."""

from __future__ import annotations


def block_type(block) -> str | None:
    if isinstance(block, dict):
        return block.get("type")
    return getattr(block, "type", None)


def block_field(block, name: str, default=None):
    if isinstance(block, dict):
        return block.get(name, default)
    return getattr(block, name, default)


def block_text(block) -> str:
    return str(block_field(block, "text", "") or "")


def is_tool_use(block) -> bool:
    return block_type(block) == "tool_use"


def is_text(block) -> bool:
    return block_type(block) == "text"
