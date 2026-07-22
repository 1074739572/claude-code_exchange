"""Tests for lookup-mode fetch guardrails."""

from harness.agent.lookup_guard import (
    LOOKUP_FORCE_ANSWER,
    LookupGuard,
    classify_fetch_result,
    is_low_value_fetch_result,
    is_web_fetch_tool,
)


def test_web_fetch_tool_detects_mcp_fetch():
    assert is_web_fetch_tool("mcp__fetch__fetch", {"url": "https://example.com"})


def test_web_fetch_tool_ignores_read_file():
    assert not is_web_fetch_tool("read_file", {"path": "README.md"})


def test_low_value_mcp_error():
    assert is_low_value_fetch_result("MCP error: status code 403")
    assert classify_fetch_result("MCP error: status code 403") == "hard_fail"


def test_low_value_openreview_shell():
    text = "Contents of https://openreview.net/group?id=ICML.cc/2026/Conference:\nLoading\n\nAbout OpenReview"
    assert is_low_value_fetch_result(text)
    assert classify_fetch_result(text) == "soft_stale"


def test_high_value_json_snippet():
    text = "x" * 200 + '{"meta": {"count": 22}, "results": [{"title": "Paper A"}]}'
    assert not is_low_value_fetch_result(text)
    assert classify_fetch_result(text) == "ok"


def test_budget_blocks_seventh_fetch():
    guard = LookupGuard(active=True)
    guard.max_fetches = 3
    for _ in range(3):
        guard.note_fetch("mcp__fetch__fetch", {"url": "https://a.com/1"})
        guard.note_result("mcp__fetch__fetch", {"url": "https://a.com/1"}, "ok " * 50)
    blocked, msg = guard.check_before_fetch(
        "mcp__fetch__fetch", {"url": "https://b.com/2"}
    )
    assert blocked
    assert "LookupGuard" in msg
    assert "memory" in msg.lower() or "THIS conversation" in msg


def test_hard_fail_does_not_burn_global_stale():
    """One PDF 404 must not kill all web — fish-bag failure mode."""
    guard = LookupGuard(active=True)
    guard.max_stale = 2
    guard.note_fetch("mcp__fetch__fetch", {"url": "https://journals.le.ac.uk/paper.pdf"})
    guard.note_result(
        "mcp__fetch__fetch",
        {"url": "https://journals.le.ac.uk/paper.pdf"},
        "MCP error: status code 404",
    )
    guard.note_fetch("mcp__fetch__fetch", {"url": "https://arxiv.org/pdf/1234.pdf"})
    guard.note_result(
        "mcp__fetch__fetch",
        {"url": "https://arxiv.org/pdf/1234.pdf"},
        "MCP error: status code 404",
    )
    # Different healthy host should still be allowed (global stale untouched).
    blocked, _ = guard.check_before_fetch(
        "mcp__fetch__fetch", {"url": "https://en.wikipedia.org/wiki/Fish"}
    )
    assert not blocked
    assert guard.consecutive_stale == 0
    # Same failed URL stays banned.
    blocked2, msg = guard.check_before_fetch(
        "mcp__fetch__fetch",
        {"url": "https://journals.le.ac.uk/paper.pdf"},
    )
    assert blocked2
    assert "already failed" in msg


def test_soft_stale_blocks_after_limit():
    guard = LookupGuard(active=True)
    guard.max_stale = 2
    for i in range(2):
        guard.note_fetch("web_search", {"query": f"q{i}"})
        guard.note_result(
            "web_search",
            {"query": f"q{i}"},
            "web_search failed for q=… (no relevant results)",
        )
    blocked, msg = guard.check_before_fetch("web_search", {"query": "q3 totally new"})
    assert blocked
    assert "no useful new information" in msg
    assert "memory" in msg.lower() or "THIS conversation" in msg


def test_robots_host_blocked_on_retry():
    guard = LookupGuard(active=True)
    url = {"url": "https://dblp.org/search/publ/api?q=test"}
    guard.note_fetch("mcp__fetch__fetch", url)
    guard.note_result("mcp__fetch__fetch", url, "MCP error: robots.txt blocked")
    blocked, msg = guard.check_before_fetch("mcp__fetch__fetch", url)
    assert blocked
    assert "dblp.org" in msg


def test_block_escalation_latches_finalize():
    guard = LookupGuard(active=True)
    guard.max_consecutive_blocks = 2
    guard.max_fetches = 100
    # Force budget so every check blocks without needing prior fetches.
    guard.fetch_count = guard.max_fetches
    assert guard.check_before_fetch("web_search", {"query": "a"})[0]
    assert not guard.note_block()
    assert guard.check_before_fetch("web_search", {"query": "b"})[0]
    assert guard.note_block()
    assert guard.finalize_latched
    blocked, msg = guard.check_before_fetch("web_search", {"query": "c"})
    assert blocked
    assert "locked" in msg.lower() or "Stop calling" in msg


def test_inactive_guard_never_blocks():
    guard = LookupGuard(active=False)
    for _ in range(10):
        guard.note_fetch("mcp__fetch__fetch", {"url": "https://x.com"})
        guard.note_result("mcp__fetch__fetch", {"url": "https://x.com"}, "MCP error")
    blocked, _ = guard.check_before_fetch("mcp__fetch__fetch", {"url": "https://x.com"})
    assert not blocked


def test_force_answer_mentions_no_memory():
    assert "memory" in LOOKUP_FORCE_ANSWER.lower()
    assert "THIS conversation" in LOOKUP_FORCE_ANSWER
