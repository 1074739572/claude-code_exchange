"""Loop nudge when model ends with thinking-only (no user-visible text)."""

from types import SimpleNamespace
from unittest import mock

from harness.context import update_context
from harness.loop import agent_loop
from harness.modes import set_mode


def _resp(content, stop_reason: str = "end_turn"):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def test_empty_reply_nudge_then_text_answer():
    set_mode("direct")
    calls = {"n": 0}

    def fake_llm(messages, context, tools, state, max_tokens):
        calls["n"] += 1
        if calls["n"] == 1:
            return _resp([{"type": "thinking", "thinking": "only internal reasoning"}])
        return _resp([{"type": "text", "text": "DIF-UNet 已找到。"}])

    messages = [{"role": "user", "content": "搜一下 DIF-UNet 这篇论文"}]
    context = update_context({}, messages)

    with mock.patch("harness.loop.call_llm", side_effect=fake_llm):
        with mock.patch("harness.loop.trigger_hooks", return_value=None):
            interrupted = agent_loop(messages, context)

    assert interrupted is False
    assert calls["n"] == 2
    blob = str(messages)
    assert "DIF-UNet 已找到" in blob
    assert "[Harness]" in blob
