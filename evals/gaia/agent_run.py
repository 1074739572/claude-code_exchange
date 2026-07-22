"""Run improved_harness agent on one GAIA validation question."""

from __future__ import annotations

import os
from typing import Any
from unittest import mock

from harness.context import update_context
from harness.loop import agent_loop
from harness.modes import set_mode
from harness.tools.dispatch import extract_text

from evals.gaia.dataset import resolve_attachment
from evals.gaia.prompt import FORCE_FINAL_ANSWER_PROMPT, build_user_prompt
from evals.gaia.scorer import extract_final_answer, extract_final_answer_from_messages


def _last_assistant_text(messages: list) -> str:
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_use" for b in content
        ):
            continue
        text = extract_text(content)
        if text.strip().startswith("[Stopped]"):
            continue
        return text
    return ""


def _count_tool_calls(messages: list) -> int:
    n = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            n += sum(
                1
                for b in content
                if isinstance(b, dict) and b.get("type") == "tool_use"
            )
    return n


def _force_finalize(messages: list, context: dict, *, rounds: int = 2) -> None:
    """One short no-tool pass so max_rounds never scores as the answer."""
    messages.append({"role": "user", "content": FORCE_FINAL_ANSWER_PROMPT})
    context = update_context(context, messages)
    with mock.patch(
        "harness.loop.get_tool_pool",
        return_value=([], {}),
    ):
        agent_loop(messages, context, max_rounds=rounds)


def run_gaia_task(
    task: dict[str, Any],
    *,
    max_rounds: int = 50,
    bootstrap_mcp: bool = True,
    web_fetch_limit: int = 18,
    web_stale_limit: int = 3,
) -> dict[str, Any]:
    """Ask the agent one GAIA question; return answer + transcript summary."""
    if bootstrap_mcp:
        try:
            from harness.mcp.pool import bootstrap_mcp_servers

            bootstrap_mcp_servers()
        except Exception as exc:  # noqa: BLE001 — eval should continue
            print(f"  MCP bootstrap warning: {type(exc).__name__}: {exc}")

    attachment = resolve_attachment(task)
    prompt = build_user_prompt(task, attachment)

    set_mode("direct")
    messages: list = [{"role": "user", "content": prompt}]
    # Cap web_search/fetch/browser thrashing (same LookupGuard as lookup mode)
    ctx = update_context(
        {
            "web_budget": True,
            "lookup_mode": False,
        },
        messages,
    )

    old_fetch = os.environ.get("HARNESS_LOOKUP_FETCH_LIMIT")
    old_stale = os.environ.get("HARNESS_LOOKUP_STALE_LIMIT")
    os.environ["HARNESS_LOOKUP_FETCH_LIMIT"] = str(web_fetch_limit)
    os.environ["HARNESS_LOOKUP_STALE_LIMIT"] = str(web_stale_limit)

    hit_cap = False
    try:
        with mock.patch("builtins.input", return_value="y"):
            agent_loop(messages, ctx, max_rounds=max_rounds)
            # Detect synthetic stop message from the loop
            for msg in reversed(messages):
                if msg.get("role") != "assistant":
                    continue
                if "[Stopped] reached max_rounds" in extract_text(msg.get("content")):
                    hit_cap = True
                break

            model_answer = extract_final_answer_from_messages(messages)
            if hit_cap or not model_answer:
                print("  forcing FINAL ANSWER (no tools)…")
                _force_finalize(messages, ctx, rounds=2)
    finally:
        if old_fetch is None:
            os.environ.pop("HARNESS_LOOKUP_FETCH_LIMIT", None)
        else:
            os.environ["HARNESS_LOOKUP_FETCH_LIMIT"] = old_fetch
        if old_stale is None:
            os.environ.pop("HARNESS_LOOKUP_STALE_LIMIT", None)
        else:
            os.environ["HARNESS_LOOKUP_STALE_LIMIT"] = old_stale

    raw = _last_assistant_text(messages)
    model_answer = extract_final_answer_from_messages(messages) or extract_final_answer(
        raw
    )

    return {
        "task_id": task["task_id"],
        "level": task["Level"],
        "ground_truth": task["Final answer"],
        "model_answer": model_answer,
        "raw_assistant": raw,
        "tool_calls": _count_tool_calls(messages),
        "attachment": str(attachment) if attachment else "",
        "hit_max_rounds": hit_cap,
        "messages": messages,
    }
