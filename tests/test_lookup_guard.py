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


def test_budget_blocks_when_limit_set():
    """Hard count is optional; only blocks when max_fetches is a positive int."""
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
    assert "at most 3" in msg


def test_default_fetch_limit_is_unlimited():
    import os

    os.environ.pop("HARNESS_LOOKUP_FETCH_LIMIT", None)
    guard = LookupGuard(active=True)
    assert guard.max_fetches is None
    guard.max_per_host = 100
    for i in range(12):
        guard.note_fetch("mcp__fetch__fetch", {"url": f"https://host{i}.example/page"})
        guard.note_result(
            "mcp__fetch__fetch",
            {"url": f"https://host{i}.example/page"},
            "ok content " * 40,
        )
    blocked, _ = guard.check_before_fetch(
        "mcp__fetch__fetch", {"url": "https://host99.example/next"}
    )
    assert not blocked


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


def test_soft_stale_blocks_search_but_allows_url_fetch():
    """After stale searches, opening ACM/arxiv must still be allowed."""
    guard = LookupGuard(active=True)
    guard.max_stale = 2
    for i in range(2):
        guard.note_fetch("web_search", {"query": f"pie menus q{i}"})
        guard.note_result(
            "web_search",
            {"query": f"pie menus q{i}"},
            "web_search failed for q=… (no relevant results)",
        )
    blocked_search, msg = guard.check_before_fetch(
        "web_search", {"query": "totally new keywords scholar"}
    )
    assert blocked_search
    assert "Do NOT search again" in msg or "no useful" in msg
    blocked_fetch, _ = guard.check_before_fetch(
        "mcp__fetch__fetch",
        {"url": "https://dl.acm.org/doi/10.1145/2702123.2702132"},
    )
    assert not blocked_fetch


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
    assert guard.max_fetches is not None
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


def test_failed_search_allows_near_reword_pie_menus():
    """Pie Menus: first search empty → reword must not be Jaccard-blocked."""
    guard = LookupGuard(active=True)
    guard.max_stale = 3
    q1 = '"Pie Menus or Linear Menus, Which Is Better?" 2015'
    q2 = "Pie Menus Linear Menus Which Is Better 2015"
    q3 = '"Pie Menus" "Linear Menus" CHI 2015'
    guard.note_fetch("web_search", {"query": q1})
    guard.note_result(
        "web_search",
        {"query": q1},
        "web_search failed for q=… (no relevant results)",
    )
    # Near-reword of a *failed* search must be allowed.
    blocked2, _ = guard.check_before_fetch("web_search", {"query": q2})
    assert not blocked2
    guard.note_fetch("web_search", {"query": q2})
    guard.note_result(
        "web_search",
        {"query": q2},
        "web_search failed for q=… (no relevant results)",
    )
    blocked3, _ = guard.check_before_fetch("web_search", {"query": q3})
    assert not blocked3
    # Exact retry of q1 still blocked.
    blocked_exact, msg = guard.check_before_fetch("web_search", {"query": q1})
    assert blocked_exact
    assert "exact query already tried" in msg


def test_ok_search_still_blocks_near_duplicate():
    guard = LookupGuard(active=True)
    guard.dup_threshold = 0.6
    q1 = "Mercedes Sosa studio albums discography wikipedia"
    q2 = "Mercedes Sosa studio albums wikipedia discography"
    # On-topic SERP: must include longest query tokens (mercedes/sosa/albums/…).
    rich = (
        "web_search (bing) q='Mercedes Sosa studio albums' — 3 result(s):\n"
        "1. Mercedes Sosa – Wikipedia\n"
        "   https://en.wikipedia.org/wiki/Mercedes_Sosa\n"
        "   Argentine singer Mercedes Sosa studio albums discography 2000 2009\n"
        "2. Discography of Mercedes Sosa\n"
        "   https://example.com/sosa-albums\n"
        "   Full studio albums list for Mercedes Sosa including Al despertar\n"
    )
    guard.note_fetch("web_search", {"query": q1})
    guard.note_result("web_search", {"query": q1}, rich)
    assert guard.consecutive_stale == 0
    assert len(guard._recent_ok_queries) == 1
    blocked, msg = guard.check_before_fetch("web_search", {"query": q2})
    assert blocked
    assert "successful" in msg or "near-identical" in msg


def test_offtopic_serp_is_soft_stale_not_ok_for_dup():
    """Blender plugin hits for an academic paper query must not lock near-dup."""
    q = '"Pie Menus or Linear Menus, Which Is Better?" 2015'
    junk = (
        "web_search (so) q='Pie Menus…' — 5 result(s):\n"
        "1. Blender插件 Better Pie Menus V0.5.3\n"
        "   https://www.houqijun.vip/plugin\n"
        "   智能弹出式菜单工具 Better Pie Menus 插件预设\n"
        "2. 什么值得买 Better Pie Menus\n"
        "   https://post.smzdm.com/p/x\n"
        "   超强快捷菜单自由定制\n"
    )
    assert classify_fetch_result(junk, tool_input={"query": q}) == "soft_stale"
    guard = LookupGuard(active=True)
    guard.max_stale = 3
    guard.note_fetch("web_search", {"query": q})
    guard.note_result("web_search", {"query": q}, junk)
    assert guard.consecutive_stale == 1
    assert guard._recent_ok_queries == []
    reword = '"Pie Menus" "Linear Menus" CHI 2015 paper authors'
    blocked, _ = guard.check_before_fetch("web_search", {"query": reword})
    assert not blocked
