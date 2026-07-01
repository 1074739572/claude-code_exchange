"""Shared tool dispatch helpers."""

from __future__ import annotations


def call_tool_handler(handler, args: dict, name: str) -> str:
    if not handler:
        return f"Unknown: {name}"
    try:
        return handler(**(args or {}))
    except TypeError as exc:
        return f"Error: {exc}"


def extract_text(content) -> str:
    if not isinstance(content, list):
        return str(content)
    return "\n".join(
        getattr(block, "text", "")
        for block in content
        if getattr(block, "type", None) == "text"
    ).strip()


def has_tool_use(content) -> bool:
    return any(getattr(block, "type", None) == "tool_use" for block in content)
