"""Simulated agent_loop with mocked LLM (no API cost)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from harness.context import update_context
from harness.loop import agent_loop
from harness.modes import set_mode

from evals.types import EvalCase


def _resp(content, stop_reason: str = "end_turn"):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def case_simulated_bash_then_answer() -> None:
    """LLM: bash echo → then final text. Assert tool ran and loop finished."""
    set_mode("direct")
    calls = {"n": 0}

    def fake_llm(messages, context, tools, state, max_tokens):
        calls["n"] += 1
        if calls["n"] == 1:
            return _resp(
                [
                    {
                        "type": "tool_use",
                        "id": "call_1",
                        "name": "bash",
                        "input": {"command": "echo EVAL_OK_42"},
                    }
                ]
            )
        # After tool result is in history, finish.
        return _resp([{"type": "text", "text": "done: EVAL_OK_42"}])

    messages = [{"role": "user", "content": "run echo and confirm"}]
    context = update_context({}, messages)

    with mock.patch("harness.loop.call_llm", side_effect=fake_llm):
        with mock.patch("harness.loop.trigger_hooks", return_value=None):
            interrupted = agent_loop(messages, context)

    assert interrupted is False
    assert calls["n"] >= 2
    blob = str(messages)
    assert "EVAL_OK_42" in blob
    # tool_result should be present
    assert "tool_result" in blob


def case_simulated_denied_bash() -> None:
    """Destructive bash without confirm → permission denial in tool_result."""
    set_mode("direct")
    calls = {"n": 0}

    def fake_llm(messages, context, tools, state, max_tokens):
        calls["n"] += 1
        if calls["n"] == 1:
            return _resp(
                [
                    {
                        "type": "tool_use",
                        "id": "call_deny",
                        "name": "bash",
                        "input": {"command": "sudo shutdown now"},
                    }
                ]
            )
        return _resp([{"type": "text", "text": "stopped"}])

    messages = [{"role": "user", "content": "shutdown please"}]
    context = update_context({}, messages)

    with mock.patch("harness.loop.call_llm", side_effect=fake_llm):
        # Keep real permission_hook; only silence log noise hooks by not patching all.
        interrupted = agent_loop(messages, context)

    assert interrupted is False
    blob = str(messages)
    assert "Permission denied" in blob


CASES = [
    EvalCase(
        "sim.bash_loop",
        "mocked LLM: bash tool then final answer",
        "simulated",
        case_simulated_bash_then_answer,
    ),
    EvalCase(
        "sim.bash_denied",
        "mocked LLM: deny-list blocks bash in loop",
        "simulated",
        case_simulated_denied_bash,
    ),
]
