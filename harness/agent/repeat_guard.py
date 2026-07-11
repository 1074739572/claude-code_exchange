"""Detect identical consecutive tool calls (agent stuck loops)."""

from __future__ import annotations

import json
import os
from typing import Any


def repeat_limit() -> int:
    raw = os.getenv("HARNESS_REPEAT_LIMIT", "3").strip()
    try:
        value = int(raw)
    except ValueError:
        return 3
    return max(2, value)


def tool_fingerprint(name: str, tool_input: dict | None) -> str:
    payload = tool_input or {}
    try:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        body = str(payload)
    return f"{name}|{body}"


class RepeatGuard:
    """Block the N-th identical tool call in a row within one agent_loop."""

    def __init__(self, limit: int | None = None) -> None:
        self.limit = limit if limit is not None else repeat_limit()
        self._last_fp: str | None = None
        self._count = 0

    def note(self, name: str, tool_input: dict | None) -> tuple[int, bool]:
        """
        Record a call. Returns (streak_count, should_block).
        should_block is True when this call would be the limit-th identical one.
        """
        fp = tool_fingerprint(name, tool_input)
        if fp == self._last_fp:
            self._count += 1
        else:
            self._last_fp = fp
            self._count = 1
        return self._count, self._count >= self.limit

    def block_message(self, name: str, streak: int) -> str:
        return (
            f"[RepeatGuard] Blocked: `{name}` was called {streak} times in a row "
            f"with identical arguments. Do NOT repeat the same call. "
            f"Reuse the previous tool_result, change the arguments (different URL/"
            f"query/path), or answer the user with what you already have."
        )
