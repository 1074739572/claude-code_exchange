"""Repair broken tool_use / tool_result pairing in message history."""

from __future__ import annotations

from harness.agent.compact import is_tool_result_message, message_has_tool_use
from harness.messages.blocks import block_field, is_tool_use


CANCELLED_TOOL_RESULT = "[Interrupted by user — tool did not finish.]"


def tool_use_ids_from_content(content) -> list[str]:
    if not isinstance(content, list):
        return []
    ids: list[str] = []
    for block in content:
        if is_tool_use(block):
            tool_id = block_field(block, "id", "")
            if tool_id:
                ids.append(tool_id)
    return ids


def tool_result_ids_from_message(message: dict) -> set[str]:
    content = message.get("content")
    if not isinstance(content, list):
        return set()
    return {
        str(block.get("tool_use_id"))
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "tool_result"
        and block.get("tool_use_id")
    }


def strip_trailing_incomplete_tool_turns(messages: list) -> int:
    """Remove trailing assistant tool_use turns without a following tool_result message."""
    removed = 0
    while messages and message_has_tool_use(messages[-1]):
        messages.pop()
        removed += 1
    return removed


def complete_partial_tool_results(
    assistant_content,
    partial_results: list[dict],
    *,
    cancelled: bool = False,
) -> list[dict]:
    """Fill missing tool_result blocks for a partial tool round."""
    expected = tool_use_ids_from_content(assistant_content)
    if not expected:
        return partial_results

    by_id = {
        str(block.get("tool_use_id")): block
        for block in partial_results
        if isinstance(block, dict) and block.get("type") == "tool_result"
    }
    filled: list[dict] = []
    for tool_id in expected:
        if tool_id in by_id:
            filled.append(by_id[tool_id])
        elif cancelled:
            filled.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": CANCELLED_TOOL_RESULT,
                }
            )
    return filled


def repair_tool_pairing(messages: list) -> tuple[list, int]:
    """
    Drop or complete messages so each tool_use is immediately followed by tool_results.

    Returns (messages, fix_count).
    """
    fixes = 0
    index = 0
    while index < len(messages):
        message = messages[index]
        if not message_has_tool_use(message):
            index += 1
            continue

        expected = tool_use_ids_from_content(message.get("content"))
        next_index = index + 1
        next_message = messages[next_index] if next_index < len(messages) else None

        if next_message and is_tool_result_message(next_message):
            got = tool_result_ids_from_message(next_message)
            if not got.issubset(set(expected)):
                del messages[index]
                fixes += 1
                continue
            missing = [tool_id for tool_id in expected if tool_id not in got]
            if missing:
                blocks = list(next_message.get("content") or [])
                for tool_id in missing:
                    blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": CANCELLED_TOOL_RESULT,
                        }
                    )
                    fixes += 1
                next_message["content"] = blocks
            index += 2
            continue

        # Orphan assistant tool_use — remove it (API rejects this shape).
        del messages[index]
        fixes += 1

    # Drop tool_result-only user messages with no matching preceding tool_use.
    index = 0
    while index < len(messages):
        message = messages[index]
        if not is_tool_result_message(message):
            index += 1
            continue
        prev = messages[index - 1] if index > 0 else None
        if prev and message_has_tool_use(prev):
            index += 1
            continue
        del messages[index]
        fixes += 1

    fixes += strip_trailing_incomplete_tool_turns(messages)
    return messages, fixes


def finalize_cancelled_tool_round(
    messages: list,
    assistant_content,
    partial_results: list[dict],
) -> None:
    """After Esc/Ctrl+C during tool execution, leave API-valid history."""
    if not message_has_tool_use({"role": "assistant", "content": assistant_content}):
        strip_trailing_incomplete_tool_turns(messages)
        return

    completed = complete_partial_tool_results(
        assistant_content, partial_results, cancelled=True
    )
    if completed:
        from harness.agent.background import build_user_content

        messages.append({"role": "user", "content": build_user_content(completed)})
        return

    if messages and message_has_tool_use(messages[-1]):
        messages.pop()
