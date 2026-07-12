"""Tests for lookup-mode fetch guardrails."""

from harness.agent.lookup_guard import (
    LookupGuard,
    is_low_value_fetch_result,
    is_web_fetch_tool,
)


def test_web_fetch_tool_detects_mcp_fetch():
    assert is_web_fetch_tool("mcp__fetch__fetch", {"url": "https://example.com"})


def test_web_fetch_tool_ignores_read_file():
    assert not is_web_fetch_tool("read_file", {"path": "README.md"})


def test_low_value_mcp_error():
    assert is_low_value_fetch_result("MCP error: status code 403")


def test_low_value_openreview_shell():
    text = "Contents of https://openreview.net/group?id=ICML.cc/2026/Conference:\nLoading\n\nAbout OpenReview"
    assert is_low_value_fetch_result(text)


def test_high_value_json_snippet():
    text = "x" * 200 + '{"meta": {"count": 22}, "results": [{"title": "Paper A"}]}'
    assert not is_low_value_fetch_result(text)


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


def test_stale_blocks_after_two_bad_results():
    guard = LookupGuard(active=True)
    guard.max_stale = 2
    guard.note_fetch("mcp__fetch__fetch", {"url": "https://a.com/1"})
    guard.note_result("mcp__fetch__fetch", {"url": "https://a.com/1"}, "MCP error: 403")
    guard.note_fetch("mcp__fetch__fetch", {"url": "https://a.com/2"})
    guard.note_result(
        "mcp__fetch__fetch", {"url": "https://a.com/2"}, "MCP error: robots.txt"
    )
    blocked, msg = guard.check_before_fetch(
        "mcp__fetch__fetch", {"url": "https://a.com/3"}
    )
    assert blocked
    assert "no useful new information" in msg


def test_robots_host_blocked_on_retry():
    guard = LookupGuard(active=True)
    url = {"url": "https://dblp.org/search/publ/api?q=test"}
    guard.note_fetch("mcp__fetch__fetch", url)
    guard.note_result("mcp__fetch__fetch", url, "MCP error: robots.txt blocked")
    blocked, msg = guard.check_before_fetch("mcp__fetch__fetch", url)
    assert blocked
    assert "dblp.org" in msg


def test_inactive_guard_never_blocks():
    guard = LookupGuard(active=False)
    for _ in range(10):
        guard.note_fetch("mcp__fetch__fetch", {"url": "https://x.com"})
        guard.note_result("mcp__fetch__fetch", {"url": "https://x.com"}, "MCP error")
    blocked, _ = guard.check_before_fetch("mcp__fetch__fetch", {"url": "https://x.com"})
    assert not blocked
