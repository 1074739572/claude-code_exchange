"""Format session history into chat-stream events for the TUI."""

from __future__ import annotations

from typing import Iterator, Literal, TypeAlias

from harness.ui.final_answer import assistant_text_blocks
from harness.ui.tool_display import (
    is_failure_tool_output,
    summarize_failure_output,
    summarize_tool_input,
)
from harness.ui.tui.events import ToolEvent

ChatKind = Literal["user", "step", "assistant", "system"]
ChatItem: TypeAlias = tuple[ChatKind, str] | ToolEvent


def _block_type(block) -> str | None:
    if isinstance(block, dict):
        return block.get("type")
    return getattr(block, "type", None)


def _block_field(block, key: str, default=None):
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def _is_tool_result_message(content) -> bool:
    if not isinstance(content, list) or not content:
        return False
    return all(_block_type(b) == "tool_result" for b in content)


def _preview_intent(text: str, limit: int = 220) -> str:
    lines = [ln.rstrip() for ln in text.strip().splitlines() if ln.strip()]
    preview = " ".join(lines)
    if len(preview) > limit:
        return preview[: limit - 1] + "…"
    return preview


def _user_visible_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if _block_type(block) == "text":
                text = _block_field(block, "text", "") or ""
                if text.strip():
                    parts.append(text.strip())
        return "\n".join(parts).strip()
    return str(content).strip() if content else ""


def _tool_results_after(messages: list, index: int) -> dict[str, str]:
    if index + 1 >= len(messages):
        return {}
    content = messages[index + 1].get("content")
    if not _is_tool_result_message(content):
        return {}
    return {
        str(_block_field(block, "tool_use_id", "") or ""): str(
            _block_field(block, "content", "") or ""
        )
        for block in content
    }


def iter_history_items(messages: list) -> Iterator[ChatItem]:
    """Yield structured items so live and restored tool calls share one UI."""
    for index, msg in enumerate(messages):
        role = msg.get("role")
        content = msg.get("content")
        if role == "user":
            if _is_tool_result_message(content):
                continue
            text = _user_visible_text(content)
            if text:
                # Internal markers: show as system, not as a user bubble
                if text.startswith("[Skill loaded:"):
                    from harness.skills_loader import parse_skill_loaded_name, skill_loaded_notice

                    name = parse_skill_loaded_name(text) or "?"
                    yield ("system", skill_loaded_notice(name))
                elif text.startswith(
                    ("[Scheduled]", "[Resume context]", "[Session resumed]", "[Inbox]")
                ):
                    yield ("system", text)
                else:
                    yield ("user", text)
            continue

        if role != "assistant":
            continue

        has_tools = False
        if isinstance(content, list):
            for block in content:
                if _block_type(block) == "tool_use":
                    has_tools = True
                    break

        if has_tools:
            result_by_id = _tool_results_after(messages, index)
            for text in assistant_text_blocks(content):
                if text.strip():
                    yield ("step", f"› {_preview_intent(text)}")
            if isinstance(content, list):
                for block in content:
                    if _block_type(block) != "tool_use":
                        continue
                    name = str(_block_field(block, "name", "") or "tool")
                    tool_input = _block_field(block, "input", {}) or {}
                    if not isinstance(tool_input, dict):
                        tool_input = {}
                    detail = summarize_tool_input(name, tool_input)
                    tool_id = str(_block_field(block, "id", "") or f"history-{index}")
                    output = result_by_id.get(tool_id, "")
                    failed = bool(output) and is_failure_tool_output(output)
                    phase = "failed" if failed else ("ok" if output else "running")
                    preview = summarize_failure_output(output) if failed else (
                        "Completed" if output else "No recorded result"
                    )
                    yield ToolEvent(
                        tool_use_id=tool_id,
                        name=name,
                        summary=detail,
                        phase=phase,
                        preview=preview,
                    )
            continue

        for text in assistant_text_blocks(content):
            if text.strip():
                yield ("assistant", text.strip())


def iter_history_events(messages: list) -> Iterator[tuple[ChatKind, str]]:
    """Compatibility flattened history used by older callers and tests."""
    for item in iter_history_items(messages):
        if isinstance(item, ToolEvent):
            suffix = f"  {item.summary}" if item.summary else ""
            yield ("step", f"● {item.name}{suffix}")
            if item.phase in ("failed", "blocked") and item.preview:
                yield ("step", f"  → {item.preview}")
            continue
        yield item
