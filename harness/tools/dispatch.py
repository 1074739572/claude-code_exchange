"""Shared tool dispatch helpers."""

from __future__ import annotations

from harness.messages.blocks import block_text, is_text, is_tool_use


def call_tool_handler(handler, args: dict, name: str) -> str:
    if not handler:
        return f"Unknown: {name}"
    try:
        return handler(**(args or {}))
    except TypeError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}"


def extract_text(content) -> str:
    if not isinstance(content, list):
        return str(content)
    return "\n".join(
        block_text(block) for block in content if is_text(block)
    ).strip()


def has_tool_use(content) -> bool:
    if not isinstance(content, list):
        return False
    return any(is_tool_use(block) for block in content)
