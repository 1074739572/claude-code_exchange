"""Compaction pipeline: prepare_context, auto compact, reactive compact."""

from __future__ import annotations

import json
import time
from pathlib import Path

from harness.agent.compact.layers import (
    COMPACT_TAIL_COUNT,
    keep_tail,
    micro_compact,
    snip_compact,
    tool_result_budget,
)
from harness.agent.compact.messages import ensure_latest_user_focus
from harness.agent.compact.sizing import estimate_size
from harness.agent.compact.summarize import summarize_history
from harness.settings import CONTEXT_LIMIT, TRANSCRIPT_DIR


def write_transcript(messages: list) -> Path:
    from harness.project.session import serialize_messages

    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    path = TRANSCRIPT_DIR / f"transcript_{int(time.time())}.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for message in serialize_messages(messages):
            handle.write(json.dumps(message, ensure_ascii=False) + "\n")
    return path


def _build_compacted(label: str, summary: str, messages: list) -> list:
    tail = keep_tail(messages, count=COMPACT_TAIL_COUNT)
    compacted = [
        {"role": "user", "content": f"[{label}]\n\n{summary}"},
        *tail,
    ]
    return ensure_latest_user_focus(compacted, messages)


def compact_history(messages: list) -> list:
    from harness.project.session_store import record_compact_boundary
    from harness.ui.tool_display import hooks_verbose

    transcript = write_transcript(messages)
    if hooks_verbose():
        print(f"  \033[36m[compact] transcript saved: {transcript}\033[0m")
    summary = summarize_history(messages)
    compacted = _build_compacted("Compacted", summary, messages)
    record_compact_boundary("auto", estimate_size(messages), transcript, compacted)
    return compacted


def reactive_compact(messages: list) -> list:
    from harness.project.session_store import record_compact_boundary
    from harness.ui.tool_display import hooks_verbose

    transcript = write_transcript(messages)
    if hooks_verbose():
        print(f"  \033[31m[reactive compact] transcript saved: {transcript}\033[0m")
    summary = summarize_history(messages)
    compacted = _build_compacted("Reactive compact", summary, messages)
    record_compact_boundary("reactive", estimate_size(messages), transcript, compacted)
    return compacted


def prepare_context(messages: list) -> list:
    messages[:] = tool_result_budget(messages)
    messages[:] = snip_compact(messages)
    messages[:] = micro_compact(messages)
    if estimate_size(messages) > CONTEXT_LIMIT:
        messages[:] = compact_history(messages)
    return messages
