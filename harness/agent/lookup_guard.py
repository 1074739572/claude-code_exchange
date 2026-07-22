"""Hard guardrails for lookup-mode web fetch loops."""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

_LOW_VALUE_MARKERS = (
    "mcp error:",
    "robots.txt",
    "status code 403",
    "status code 400",
    "status code 429",
    "error: timeout",
    "failed to fetch",
    "permission denied",
    "no matching chunks",
    "connection issue",
    "web_search failed",
)

_OPENREVIEW_SHELL_RE = re.compile(
    r"loading.*about openreview",
    re.IGNORECASE | re.DOTALL,
)


def lookup_fetch_limit() -> int:
    raw = os.getenv("HARNESS_LOOKUP_FETCH_LIMIT", "6").strip()
    try:
        value = int(raw)
    except ValueError:
        return 6
    return max(1, value)


def lookup_stale_limit() -> int:
    raw = os.getenv("HARNESS_LOOKUP_STALE_LIMIT", "2").strip()
    try:
        value = int(raw)
    except ValueError:
        return 2
    return max(1, value)


def is_web_fetch_tool(name: str, tool_input: dict | None = None) -> bool:
    if name == "web_search":
        return True
    if name.startswith("mcp__fetch__"):
        return True
    if name.startswith("mcp__playwright__"):
        return True
    if name != "bash":
        return False
    command = str((tool_input or {}).get("command", "")).lower()
    return any(
        token in command
        for token in ("curl ", "wget ", "invoke-webrequest", "fetch ")
    )


def is_low_value_fetch_result(output: str) -> bool:
    text = str(output).strip()
    if not text:
        return True
    low = text.lower()
    if any(marker in low for marker in _LOW_VALUE_MARKERS):
        return True
    if len(text) < 120:
        return True
    if _OPENREVIEW_SHELL_RE.search(text) and len(text) < 1200:
        return True
    return False


def _url_key(tool_input: dict | None) -> str:
    payload = tool_input or {}
    url = str(payload.get("url", "")).strip()
    if not url:
        # web_search uses query=; still track as a host-less key so budget applies
        query = str(payload.get("query", "")).strip()
        if query:
            return f"web_search:{query.lower()[:120]}"
        return ""
    parsed = urlparse(url)
    return f"{parsed.netloc}{parsed.path}".lower().rstrip("/")


class LookupGuard:
    """Block runaway fetch loops during lookup-mode user turns."""

    def __init__(self, *, active: bool) -> None:
        self.active = active
        self.fetch_count = 0
        self.consecutive_stale = 0
        self._blocked_hosts: set[str] = set()
        self.max_fetches = lookup_fetch_limit()
        self.max_stale = lookup_stale_limit()

    def check_before_fetch(self, name: str, tool_input: dict | None) -> tuple[bool, str]:
        if not self.active or not is_web_fetch_tool(name, tool_input):
            return False, ""
        if self.fetch_count >= self.max_fetches:
            return True, self._budget_message()
        if self.consecutive_stale >= self.max_stale:
            return True, self._stale_message()
        host = _url_key(tool_input)
        if host and host in self._blocked_hosts:
            return True, self._host_block_message(host)
        return False, ""

    def note_fetch(self, name: str, tool_input: dict | None) -> None:
        if self.active and is_web_fetch_tool(name, tool_input):
            self.fetch_count += 1

    def note_result(self, name: str, tool_input: dict | None, output: str) -> None:
        if not self.active or not is_web_fetch_tool(name, tool_input):
            return
        if is_low_value_fetch_result(output):
            self.consecutive_stale += 1
            host = _url_key(tool_input)
            low = str(output).lower()
            if host and any(
                token in low
                for token in ("robots.txt", "status code 403", "status code 429")
            ):
                self._blocked_hosts.add(host)
        else:
            self.consecutive_stale = 0

    def _budget_message(self) -> str:
        return (
            f"[LookupGuard] Blocked: lookup mode allows at most {self.max_fetches} "
            f"web fetch calls per user turn ({self.fetch_count} already used). "
            "Stop fetching. Answer the user now: say 有/没有 (or found/not found), "
            "cite what you already have, and note blocked sources briefly."
        )

    def _stale_message(self) -> str:
        return (
            f"[LookupGuard] Blocked: {self.consecutive_stale} consecutive fetch "
            "results had no useful new information (errors, robots, empty shells). "
            "Do NOT try another URL. Answer the user now with 公开检索未找到 or "
            "partial findings from earlier successful results."
        )

    def _host_block_message(self, host: str) -> str:
        return (
            f"[LookupGuard] Blocked: {host} already failed (robots/403/429). "
            "Do not retry this host. Answer the user with what you have."
        )
