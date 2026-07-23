"""Hard guardrails for lookup-mode web fetch loops.

* **Optional hard fetch count** — off by default; set ``HARNESS_LOOKUP_FETCH_LIMIT``
  to a positive int only if you want a hard cap.
* **Near-duplicate queries** — Jaccard only against *successful* searches;
  failed/empty searches may be reworded (exact same query still blocked).
* **Per-host hammering** — many paths on the same site.
* **Stale dimensions** — a single URL 404/robots bans that URL only;
  soft-stale stops further *searches* (URL fetch still allowed).
* **Block escalation** — consecutive blocked attempts latch a force-answer
  signal so the loop can strip tools instead of soft-nudge forever.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from typing import Literal
from urllib.parse import urlparse

_HARD_FAIL_MARKERS = (
    "robots.txt",
    "status code 403",
    "status code 404",
    "status code 400",
    "status code 429",
    "error: timeout",
    "failed to fetch",
    "permission denied",
    "connection issue",
    "mcp error:",
)

_SOFT_STALE_MARKERS = (
    "no matching chunks",
    "web_search failed",
    "no relevant results",
)

_OPENREVIEW_SHELL_RE = re.compile(
    r"loading.*about openreview",
    re.IGNORECASE | re.DOTALL,
)

# Shared with loop when consecutive blocks escalate.
LOOKUP_FORCE_ANSWER = (
    "[LookupGuard] Stop calling web tools now.\n"
    "Answer using ONLY evidence fetched and read in THIS conversation "
    "(tool results above). Do NOT invent specific titles, numbers, names, "
    "or scene headings from memory.\n"
    "If the fact was never verified, give your most defensible guess and "
    "treat it as unverified — or say you could not verify it.\n"
    "Prefer `FINAL ANSWER: ...` if that format was requested. "
    "Plain text reply only; no more tool calls."
)

ResultKind = Literal["ok", "hard_fail", "soft_stale"]


def lookup_fetch_limit() -> int | None:
    """Optional hard cap on web tool calls per turn.

    Default **None** (unlimited): Claude Code–style — no fixed fetch quota.
    Set ``HARNESS_LOOKUP_FETCH_LIMIT`` to a positive int to re-enable a hard cap.
    ``0`` / empty / negative → unlimited.
    """
    raw = os.getenv("HARNESS_LOOKUP_FETCH_LIMIT", "0").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    if value <= 0:
        return None
    return value


def lookup_stale_limit() -> int:
    raw = os.getenv("HARNESS_LOOKUP_STALE_LIMIT", "2").strip()
    try:
        value = int(raw)
    except ValueError:
        return 2
    return max(1, value)


def lookup_host_limit() -> int:
    """Max fetches allowed against a single host before we block it."""
    raw = os.getenv("HARNESS_LOOKUP_HOST_LIMIT", "4").strip()
    try:
        value = int(raw)
    except ValueError:
        return 4
    return max(1, value)


def lookup_dup_threshold() -> float:
    """Jaccard similarity above which two queries are considered near-duplicates."""
    raw = os.getenv("HARNESS_LOOKUP_DUP_THRESHOLD", "0.6").strip()
    try:
        value = float(raw)
    except ValueError:
        return 0.6
    return max(0.3, min(0.95, value))


def lookup_block_escalate_limit() -> int:
    """Consecutive LookupGuard blocks before the loop force-finalizes."""
    raw = os.getenv("HARNESS_LOOKUP_BLOCK_ESCALATE", "2").strip()
    try:
        value = int(raw)
    except ValueError:
        return 2
    return max(1, value)


_STOPWORDS = frozenset(
    {
        "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or",
        "is", "are", "was", "were", "be", "by", "with", "from", "as", "that",
        "this", "it", "its", "do", "does", "did", "how", "what", "who",
        "when", "where", "which", "why", "find", "list", "all", "any",
    }
)


def _query_tokens(text: str) -> set[str]:
    """Lowercased alphanumeric tokens, minus stopwords, for similarity comparison."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if len(t) > 1 and t not in _STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


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


def is_low_value_fetch_result(output: str, tool_input: dict | None = None) -> bool:
    return classify_fetch_result(output, tool_input=tool_input) != "ok"


def _web_search_on_topic(query: str, output: str) -> bool:
    """False when SERP is long but off-topic (keyword collision junk).

    Pie Menus case: query asks for a 2015 academic paper; SO returned Blender
    plugin pages that share \"Pie Menus\" / \"Better\" but miss distinctive
    terms like \"linear\". Require the longest query tokens to appear in hits.
    """
    tokens = _query_tokens(query)
    key = sorted(
        (t for t in tokens if len(t) >= 4 and not t.isdigit()),
        key=len,
        reverse=True,
    )
    if len(key) < 2:
        return len(output) >= 120
    need = key[: min(3, len(key))]
    low = output.lower()
    hits = sum(1 for t in need if t in low)
    return hits >= len(need)


def classify_fetch_result(
    output: str, *, tool_input: dict | None = None
) -> ResultKind:
    """Split hard URL failures from soft/irrelevant stale.

    hard_fail → ban this URL/host only; do NOT burn global consecutive_stale.
    soft_stale → empty / irrelevant / failed search; counts toward global stale.
    """
    text = str(output).strip()
    if not text:
        return "soft_stale"
    low = text.lower()
    if any(marker in low for marker in _HARD_FAIL_MARKERS):
        return "hard_fail"
    if any(marker in low for marker in _SOFT_STALE_MARKERS):
        return "soft_stale"
    if len(text) < 120:
        return "soft_stale"
    if _OPENREVIEW_SHELL_RE.search(text) and len(text) < 1200:
        return "soft_stale"
    # web_search SERP: long off-topic pages still count as soft_stale so the
    # agent can reword (do not enter near-dup \"successful\" history).
    query = _query_text(tool_input)
    if query and (
        low.startswith("web_search")
        or " result(s):" in text[:100].lower()
        or "<persisted-output" in low and "web_search" in low
    ):
        # Persisted preview may be short; if full body was inlined, check it.
        body = text
        if not _web_search_on_topic(query, body):
            return "soft_stale"
    return "ok"


def _url_key(tool_input: dict | None) -> str:
    payload = tool_input or {}
    url = str(payload.get("url", "")).strip()
    if not url:
        query = str(payload.get("query", "")).strip()
        if query:
            return f"web_search:{query.lower()[:120]}"
        return ""
    parsed = urlparse(url)
    return f"{parsed.netloc}{parsed.path}".lower().rstrip("/")


def _host_key(tool_input: dict | None) -> str:
    """Host-only key for per-host hammering detection (empty for web_search)."""
    payload = tool_input or {}
    url = str(payload.get("url", "")).strip()
    if not url:
        return ""
    parsed = urlparse(url)
    return parsed.netloc.lower()


def _query_text(tool_input: dict | None) -> str:
    """Extract the query string for near-duplicate detection (web_search only)."""
    payload = tool_input or {}
    return str(payload.get("query", "")).strip()


_EVIDENCE_TAIL = (
    " Use ONLY evidence fetched/read in THIS conversation. "
    "Do NOT invent specific titles, numbers, names, or headings from memory. "
    "If unverified, say so or give a clearly tentative best guess. "
    "Prefer `FINAL ANSWER: ...` if that format was requested."
)


class LookupGuard:
    """Block runaway fetch loops during lookup-mode user turns."""

    def __init__(self, *, active: bool) -> None:
        self.active = active
        self.fetch_count = 0
        self.consecutive_stale = 0
        self.consecutive_blocks = 0
        self.finalize_latched = False
        self._blocked_urls: set[str] = set()
        self._blocked_hosts: set[str] = set()
        self._host_counts: Counter[str] = Counter()
        # Near-dup Jaccard only against queries that returned useful results.
        # Failed searches must be reformulable (Pie Menus: first miss → reword).
        self._recent_ok_queries: list[set[str]] = []
        self._recent_ok_query_texts: list[str] = []
        # Exact query strings already attempted (any outcome) — ban identical retry.
        self._tried_queries: set[str] = set()
        self.max_fetches = lookup_fetch_limit()
        self.max_stale = lookup_stale_limit()
        self.max_per_host = lookup_host_limit()
        self.dup_threshold = lookup_dup_threshold()
        self.max_consecutive_blocks = lookup_block_escalate_limit()

    def check_before_fetch(self, name: str, tool_input: dict | None) -> tuple[bool, str]:
        if not self.active or not is_web_fetch_tool(name, tool_input):
            return False, ""
        if self.finalize_latched:
            return True, self._escalate_message()
        if self.max_fetches is not None and self.fetch_count >= self.max_fetches:
            return True, self._budget_message()
        # Soft-stale budget: stop more *searches*, but still allow opening a
        # concrete URL (换源). Pie Menus: three empty SERPs must not block ACM.
        if self.consecutive_stale >= self.max_stale:
            url = str((tool_input or {}).get("url", "")).strip()
            if not url:
                return True, self._stale_message()
        url_key = _url_key(tool_input)
        if url_key and url_key in self._blocked_urls:
            return True, self._url_block_message(url_key)
        host_only = _host_key(tool_input)
        if host_only and host_only in self._blocked_hosts:
            return True, self._host_block_message(host_only)
        if host_only and self._host_counts[host_only] >= self.max_per_host:
            self._blocked_hosts.add(host_only)
            return True, self._host_quota_message(host_only)
        query = _query_text(tool_input)
        if query:
            norm = query.lower().strip()
            if norm in self._tried_queries:
                return True, self._exact_query_message(query)
            dup = self._find_near_duplicate(query)
            if dup is not None:
                return True, self._dup_message(dup, query)
        return False, ""

    def note_block(self) -> bool:
        """Record a blocked web attempt. True → caller should force-finalize."""
        if not self.active:
            return False
        self.consecutive_blocks += 1
        if self.consecutive_blocks >= self.max_consecutive_blocks:
            self.finalize_latched = True
            return True
        return False

    def note_allowed(self) -> None:
        """A web tool actually ran (not blocked) — reset block streak."""
        if self.active and not self.finalize_latched:
            self.consecutive_blocks = 0

    def _find_near_duplicate(self, query: str) -> str | None:
        """Compare only against prior *successful* searches (not failed ones)."""
        tokens = _query_tokens(query)
        if not tokens:
            return None
        for prev_tokens, prev_text in zip(
            self._recent_ok_queries, self._recent_ok_query_texts
        ):
            sim = _jaccard(tokens, prev_tokens)
            if sim >= self.dup_threshold:
                return prev_text
        return None

    def note_fetch(self, name: str, tool_input: dict | None) -> None:
        if not self.active or not is_web_fetch_tool(name, tool_input):
            return
        self.note_allowed()
        self.fetch_count += 1
        host_only = _host_key(tool_input)
        if host_only:
            self._host_counts[host_only] += 1
        query = _query_text(tool_input)
        if query:
            # Remember exact attempt immediately; Jaccard list waits for ok result.
            self._tried_queries.add(query.lower().strip())

    def note_result(self, name: str, tool_input: dict | None, output: str) -> None:
        if not self.active or not is_web_fetch_tool(name, tool_input):
            return
        kind = classify_fetch_result(output, tool_input=tool_input)
        url_key = _url_key(tool_input)
        host_only = _host_key(tool_input)
        query = _query_text(tool_input)
        if kind == "ok":
            self.consecutive_stale = 0
            if query:
                self._recent_ok_queries.append(_query_tokens(query))
                self._recent_ok_query_texts.append(query)
                if len(self._recent_ok_queries) > 20:
                    self._recent_ok_queries.pop(0)
                    self._recent_ok_query_texts.pop(0)
            return
        if kind == "hard_fail":
            # Ban this URL (and host on robots/403/429); do NOT burn global stale.
            if url_key:
                self._blocked_urls.add(url_key)
            low = str(output).lower()
            if host_only and any(
                token in low
                for token in ("robots.txt", "status code 403", "status code 429")
            ):
                self._blocked_hosts.add(host_only)
            return
        # soft_stale — empty / irrelevant / failed search
        # Do NOT add to near-dup history: agent must be free to reword (Pie Menus).
        self.consecutive_stale += 1

    def _budget_message(self) -> str:
        return (
            f"[LookupGuard] Blocked: at most {self.max_fetches} web tool calls "
            f"per turn ({self.fetch_count} already used)."
            + _EVIDENCE_TAIL
        )

    def _stale_message(self) -> str:
        return (
            f"[LookupGuard] Blocked: {self.consecutive_stale} consecutive web "
            "searches/calls returned no useful new information. Do NOT search "
            "again with similar queries — open a specific URL from clues you "
            "have (arxiv / ACM / Wikipedia), or answer from evidence already "
            "in this conversation."
            + _EVIDENCE_TAIL
        )

    def _url_block_message(self, url_key: str) -> str:
        return (
            f"[LookupGuard] Blocked: {url_key} already failed "
            "(404/robots/403/timeout). Do NOT retry this URL — try a DIFFERENT "
            "source or answer from what you already fetched."
            + _EVIDENCE_TAIL
        )

    def _host_block_message(self, host: str) -> str:
        return (
            f"[LookupGuard] Blocked: host {host} already failed "
            "(robots/403/429). Do NOT retry this host — switch source or answer."
            + _EVIDENCE_TAIL
        )

    def _host_quota_message(self, host: str) -> str:
        return (
            f"[LookupGuard] Blocked: already fetched {self.max_per_host} times "
            f"from {host}. Fetch a DIFFERENT source or answer from what you have."
            + _EVIDENCE_TAIL
        )

    def _exact_query_message(self, query: str) -> str:
        return (
            f"[LookupGuard] Blocked: exact query already tried ({query!r}). "
            "Change keywords substantially (add venue/year/author) or open a "
            "known URL — do not paste the same search again."
            + _EVIDENCE_TAIL
        )

    def _dup_message(self, prev: str, current: str) -> str:
        return (
            "[LookupGuard] Blocked: this web_search is near-identical to a "
            f"recent *successful* one ({prev!r} ≈ {current!r}). Change the query "
            "substantially, fetch a DIFFERENT source, or answer from what you have."
            + _EVIDENCE_TAIL
        )

    def _escalate_message(self) -> str:
        return (
            "[LookupGuard] Blocked: web tools are locked after repeated blocks. "
            + LOOKUP_FORCE_ANSWER.removeprefix("[LookupGuard] ")
        )
