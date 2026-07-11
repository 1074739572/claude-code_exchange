"""Human-facing summaries for tool calls (full payloads still go to the model)."""

from __future__ import annotations

import os
import re
from typing import Any


def tool_ui_mode() -> str:
    """compact (default) | verbose | off"""
    raw = os.getenv("HARNESS_TOOL_UI", "compact").strip().lower()
    if raw in {"compact", "verbose", "off", "quiet"}:
        return "off" if raw == "quiet" else raw
    return "compact"


def hooks_verbose() -> bool:
    return os.getenv("HARNESS_VERBOSE", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    } or tool_ui_mode() == "verbose"


def _short(text: str, limit: int = 72) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def summarize_tool_input(name: str, tool_input: dict | None) -> str:
    """One-line human summary of what the tool is about to do."""
    args = tool_input or {}
    if name == "bash":
        return _short(str(args.get("command", "")), 90)
    if name in {"read_file", "write_file", "edit_file"}:
        path = str(args.get("path", ""))
        extra = ""
        if name == "read_file" and args.get("offset") is not None:
            extra = f" @{args.get('offset')}"
            if args.get("limit") is not None:
                extra += f"+{args.get('limit')}"
        return _short(path + extra, 90)
    if name == "glob":
        return _short(str(args.get("pattern", "")), 90)
    if name == "todo_write":
        todos = args.get("todos") or []
        return f"{len(todos)} item(s)" if isinstance(todos, list) else "update"
    if name.startswith("mcp__"):
        keys = [k for k in ("url", "path", "selector", "query", "command") if k in args]
        if keys:
            return _short(f"{keys[0]}={args.get(keys[0])}", 90)
        return "…"
    if name == "github_request":
        return _short(f"{args.get('method', 'GET')} {args.get('path', '')}", 90)
    # Generic: prefer path/query/command
    for key in ("path", "query", "command", "url", "name", "prompt"):
        if key in args and args[key] not in (None, ""):
            return _short(f"{key}={args[key]}", 90)
    if not args:
        return ""
    try:
        import json

        return _short(json.dumps(args, ensure_ascii=False), 90)
    except TypeError:
        return _short(str(args), 90)


def summarize_tool_output(
    name: str,
    output: Any,
    *,
    tool_input: dict | None = None,
) -> str:
    """One-line (or short) human preview of the tool result."""
    text = str(output if output is not None else "")
    stripped = text.strip()
    lower = stripped.lower()

    if lower.startswith("permission denied") or lower.startswith("error:"):
        return _short(stripped, 100)

    if name == "bash":
        if stripped in {"(no output)", ""}:
            return "ok (no output)"
        lines = stripped.splitlines()
        if len(lines) == 1 and len(stripped) <= 100:
            return stripped
        return f"{len(lines)} lines · {_short(lines[0], 60)}"

    if name == "read_file":
        if stripped.startswith("Error:"):
            return _short(stripped, 100)
        lines = text.splitlines()
        path = (tool_input or {}).get("path", "")
        head = _short(lines[0] if lines else "", 50)
        suffix = f" · {head}" if head else ""
        return f"{len(lines)} lines{suffix}"

    if name in {"write_file", "edit_file"}:
        return _short(stripped, 100) or "ok"

    if name == "glob":
        if stripped.startswith("(no matches)") or stripped == "":
            return "0 matches"
        n = len([ln for ln in stripped.splitlines() if ln.strip()])
        return f"{n} match(es)"

    if name == "todo_write":
        return _short(stripped.splitlines()[0] if stripped else "updated", 80)

    # Default
    if not stripped:
        return "ok"
    lines = stripped.splitlines()
    if len(stripped) <= 100 and len(lines) <= 2:
        return stripped.replace("\n", " ⏎ ")
    return f"{len(stripped)} chars · {_short(lines[0], 55)}"
