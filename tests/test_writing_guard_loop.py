"""Simulated loop: writing mode requires rag_search before output write."""

from types import SimpleNamespace
from unittest import mock

from harness.context import update_context
from harness.loop import agent_loop
from harness.modes import set_mode


def _resp(content, stop_reason: str = "end_turn"):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def test_writing_guard_blocks_write_until_search():
    set_mode("direct")
    calls = {"n": 0}

    def fake_llm(messages, context, tools, state, max_tokens):
        calls["n"] += 1
        if calls["n"] == 1:
            return _resp(
                [
                    {
                        "type": "tool_use",
                        "id": "w1",
                        "name": "write_file",
                        "input": {"path": "output/01_引言.md", "content": "draft"},
                    }
                ]
            )
        if calls["n"] == 2:
            return _resp(
                [
                    {
                        "type": "tool_use",
                        "id": "s1",
                        "name": "rag_search",
                        "input": {"query": "引言 结构"},
                    }
                ]
            )
        return _resp([{"type": "text", "text": "done"}])

    messages = [{"role": "user", "content": "仿写引言章节"}]
    context = update_context({"writing_mode": True}, messages)

    with mock.patch("harness.loop.call_llm", side_effect=fake_llm):
        with mock.patch("harness.loop.trigger_hooks", return_value=None):
            with mock.patch(
                "harness.loop.call_tool_handler",
                side_effect=lambda h, args, name: f"ok:{name}",
            ):
                interrupted = agent_loop(messages, context)

    assert interrupted is False
    blob = str(messages)
    assert "WritingGuard" in blob
    assert "ok:rag_search" in blob
