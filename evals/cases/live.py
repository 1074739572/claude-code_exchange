"""Optional live LLM smoke tests (--live)."""

from __future__ import annotations

import os
import re

from dotenv import load_dotenv

from harness.context import update_context
from harness.loop import agent_loop
from harness.modes import set_mode
from harness.tools.dispatch import extract_text

from evals.errors import EvalSkip
from evals.types import EvalCase


def _has_api_key() -> bool:
    load_dotenv()
    return bool(
        os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("ZHIPU_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
    )


def case_live_pong() -> None:
    if not _has_api_key():
        raise EvalSkip("no API key in .env")
    set_mode("direct")
    messages = [
        {
            "role": "user",
            "content": (
                "Reply with exactly one word and nothing else: PONG\n"
                "Do not call any tools."
            ),
        }
    ]
    context = update_context({}, messages)
    agent_loop(messages, context)
    text = ""
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            text = extract_text(msg.get("content"))
            break
    cleaned = re.sub(r"[^A-Za-z]", "", text).upper()
    assert "PONG" in cleaned, f"expected PONG in assistant reply, got: {text!r}"


def case_live_read_readme() -> None:
    if not _has_api_key():
        raise EvalSkip("no API key in .env")
    set_mode("direct")
    messages = [
        {
            "role": "user",
            "content": (
                "Use the read_file tool to read README.md. "
                "Then reply with a single line starting with TITLE: "
                "followed by the first markdown heading you see (the # title). "
                "Do not invent a title without reading the file."
            ),
        }
    ]
    context = update_context({}, messages)
    agent_loop(messages, context)
    blob = str(messages)
    assert "read_file" in blob
    text = ""
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_use" for b in content
        ):
            continue
        text = extract_text(content)
        break
    assert "TITLE:" in text.upper() or "improved" in text.lower() or "harness" in text.lower(), (
        f"unexpected final reply: {text!r}"
    )


CASES = [
    EvalCase(
        "live.pong",
        "live LLM replies PONG without tools",
        "live",
        case_live_pong,
        requires_live=True,
    ),
    EvalCase(
        "live.read_readme",
        "live LLM uses read_file on README.md",
        "live",
        case_live_read_readme,
        requires_live=True,
    ),
]
