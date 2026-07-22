"""Format session history into chat-stream events for the TUI."""

from __future__ import annotations

from typing import Iterator, Literal

from harness.ui.final_answer import assistant_text_blocks
from harness.ui.tool_display import (
    is_failure_tool_output,
    summarize_failure_output,
    summarize_tool_input,
)

ChatKind = Literal["user", "step", "assistant", "system"]


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


def iter_history_events(messages: list) -> Iterator[tuple[ChatKind, str]]:
    """Yield (kind, text) for hydrating the merged chat pane (S1 + H1 + R3)."""
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if role == "user":
            if _is_tool_result_message(content):
                for block in content:
                    output = _block_field(block, "content", "")
                    if is_failure_tool_output(output):
                        yield ("step", f"  → {summarize_failure_output(output)}")
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
                    suffix = f"  {detail}" if detail else ""
                    yield ("step", f"● {name}{suffix}")
            continue

        for text in assistant_text_blocks(content):
            if text.strip():
                yield ("assistant", text.strip())
