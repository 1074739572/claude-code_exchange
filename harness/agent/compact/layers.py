"""Per-layer compaction: budget, snip, micro, and tail retention."""

from __future__ import annotations

from harness.agent.compact.messages import (
    collect_tool_results,
    is_tool_result_message,
    message_has_tool_use,
)
from harness.agent.compact.persist import (
    _MICRO_COMPACT_MIN_CHARS,
    is_persisted_output,
    persist_large_output,
    persist_recallable_output,
)
from harness.settings import KEEP_RECENT_TOOL_RESULTS

COMPACT_TAIL_COUNT = 5


def tool_result_budget(messages: list, max_bytes: int = 200_000) -> list:
    if not messages:
        return messages
    last = messages[-1]
    content = last.get("content")
    if last.get("role") != "user" or not isinstance(content, list):
        return messages
    blocks = [
        (index, block)
        for index, block in enumerate(content)
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
    total = sum(len(str(block.get("content", ""))) for _, block in blocks)
    if total <= max_bytes:
        return messages
    for _, block in sorted(
        blocks,
        key=lambda pair: len(str(pair[1].get("content", ""))),
        reverse=True,
    ):
        if total <= max_bytes:
            break
        text = str(block.get("content", ""))
        if is_persisted_output(text):
            continue
        block["content"] = persist_large_output(block.get("tool_use_id", "unknown"), text)
        total = sum(len(str(item.get("content", ""))) for _, item in blocks)
    return messages


def snip_compact(messages: list, max_messages: int = 50) -> list:
    if len(messages) <= max_messages:
        return messages
    head_end = 3
    tail_start = len(messages) - (max_messages - 3)
    if head_end > 0 and message_has_tool_use(messages[head_end - 1]):
        while head_end < len(messages) and is_tool_result_message(messages[head_end]):
            head_end += 1
    if (
        tail_start > 0
        and tail_start < len(messages)
        and is_tool_result_message(messages[tail_start])
        and message_has_tool_use(messages[tail_start - 1])
    ):
        tail_start -= 1
    if head_end >= tail_start:
        return messages
    snipped = tail_start - head_end
    return (
        messages[:head_end]
        + [{"role": "user", "content": f"[snipped {snipped} messages]"}]
        + messages[tail_start:]
    )


def micro_compact(messages: list) -> list:
    tool_results = collect_tool_results(messages)
    if len(tool_results) <= KEEP_RECENT_TOOL_RESULTS:
        return messages
    for message_index, block_index, block in tool_results[:-KEEP_RECENT_TOOL_RESULTS]:
        text = str(block.get("content", ""))
        if is_persisted_output(text):
            continue
        if len(text) <= _MICRO_COMPACT_MIN_CHARS:
            continue
        tool_id = block.get("tool_use_id") or f"micro-{message_index}-{block_index}"
        block["content"] = persist_recallable_output(tool_id, text)
    return messages


def keep_tail(messages: list, count: int = 5) -> list:
    tail_start = max(0, len(messages) - count)
    if (
        tail_start > 0
        and tail_start < len(messages)
        and is_tool_result_message(messages[tail_start])
        and message_has_tool_use(messages[tail_start - 1])
    ):
        tail_start -= 1
    return messages[tail_start:]
