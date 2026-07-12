"""Simulated loop tests for LookupGuard integration."""

from types import SimpleNamespace
from unittest import mock

from harness.context import update_context
from harness.loop import agent_loop
from harness.modes import set_mode


def _resp(content, stop_reason: str = "end_turn"):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def test_lookup_guard_blocks_after_stale_fetches():
    set_mode("direct")
    calls = {"n": 0}

    def fake_llm(messages, context, tools, state, max_tokens):
        calls["n"] += 1
        if calls["n"] <= 3:
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
    assert calls["n"] <= 4
