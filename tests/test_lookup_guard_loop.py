"""Simulated loop tests for LookupGuard integration."""

from types import SimpleNamespace
from unittest import mock

from harness.context import update_context
from harness.loop import agent_loop
from harness.modes import set_mode


def _resp(content, stop_reason: str = "end_turn"):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def test_lookup_guard_blocks_host_after_403_and_escalates():
    """403 bans host; retries block; second block force-finalizes (no tools)."""
    set_mode("direct")
    calls = {"n": 0}

    def fake_llm(messages, context, tools, state, max_tokens):
        calls["n"] += 1
        # After escalate, tools are stripped — model must answer in text.
        if not tools:
            return _resp([{"type": "text", "text": "公开检索未找到"}])
        if calls["n"] <= 5:
            return _resp(
                [
                    {
                        "type": "tool_use",
                        "id": f"call_{calls['n']}",
                        "name": "mcp__fetch__fetch",
                        "input": {"url": f"https://blocked.example/{calls['n']}"},
                    }
                ]
            )
        return _resp([{"type": "text", "text": "公开检索未找到"}])

    messages = [{"role": "user", "content": "查找一下某论文有没有"}]
    context = update_context({"lookup_mode": True}, messages)

    with mock.patch("harness.loop.call_llm", side_effect=fake_llm):
        with mock.patch("harness.loop.trigger_hooks", return_value=None):
            with mock.patch(
                "harness.loop.call_tool_handler",
                return_value="MCP error: status code 403",
            ):
                interrupted = agent_loop(messages, context)

    assert interrupted is False
    blob = str(messages)
    assert "LookupGuard" in blob
    assert "Stop calling web tools" in blob or "forcing answer" in blob.lower()
    assert calls["n"] <= 5


def test_hard_fail_allows_other_hosts_in_loop():
    """One 404 must not block a different healthy host (mode B)."""
    set_mode("direct")
    calls = {"n": 0}
    fetched: list[str] = []

    def fake_llm(messages, context, tools, state, max_tokens):
        calls["n"] += 1
        if calls["n"] == 1:
            return _resp(
                [
                    {
                        "type": "tool_use",
                        "id": "call_1",
                        "name": "mcp__fetch__fetch",
                        "input": {"url": "https://journals.le.ac.uk/paper.pdf"},
                    }
                ]
            )
        if calls["n"] == 2:
            return _resp(
                [
                    {
                        "type": "tool_use",
                        "id": "call_2",
                        "name": "mcp__fetch__fetch",
                        "input": {"url": "https://en.wikipedia.org/wiki/Fish"},
                    }
                ]
            )
        return _resp([{"type": "text", "text": "done"}])

    def fake_handler(name, tool_input, messages=None):
        url = tool_input.get("url", "")
        fetched.append(url)
        if "journals" in url:
            return "MCP error: status code 404"
        return "Fish are aquatic animals. " * 20

    messages = [{"role": "user", "content": "find fish bag fact"}]
    context = update_context({"lookup_mode": True}, messages)

    with mock.patch("harness.loop.call_llm", side_effect=fake_llm):
        with mock.patch("harness.loop.trigger_hooks", return_value=None):
            with mock.patch(
                "harness.loop.call_tool_handler",
                side_effect=fake_handler,
            ):
                interrupted = agent_loop(messages, context)

    assert interrupted is False
    assert "https://en.wikipedia.org/wiki/Fish" in fetched
    assert "already failed" not in str(messages) or "wikipedia" not in str(messages).lower()
