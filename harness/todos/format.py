"""Format session todos for prompts, tool results, and reminders."""

from __future__ import annotations

from harness.todos.state import get_todos, rounds_since_todo_update


def _status_icon(status: str) -> str:
    if status == "completed":
        return "[x]"
    if status == "in_progress":
        return "[>]"
    return "[ ]"


def format_todos_for_prompt(todos: list[dict[str, str]] | None = None) -> str:
    todos = todos if todos is not None else get_todos()
    if not todos:
        return ""
    lines = [
        "Current session todos (single source of truth — update via todo_write with the FULL list):"
    ]
    for index, todo in enumerate(todos, 1):
        status = todo["status"]
        label = todo["activeForm"] if status == "in_progress" else todo["content"]
        lines.append(f"{index}. {_status_icon(status)} {label} ({status})")
    lines.append(
        "Discipline: exactly one in_progress; mark completed immediately when done."
    )
    return "\n".join(lines)


def format_todos_tool_result(todos: list[dict[str, str]]) -> str:
    lines = [f"Updated {len(todos)} todo(s). Current list:"]
    for index, todo in enumerate(todos, 1):
        status = todo["status"]
        if status == "completed":
            lines.append(f"{index}. [x] {todo['content']}")
        elif status == "in_progress":
            lines.append(f"{index}. [>] {todo['activeForm']} (in progress)")
        else:
            lines.append(f"{index}. [ ] {todo['content']} (pending)")
    lines.append("")
    lines.append(
        "Remember: pass the FULL list on every todo_write call; "
        "exactly one in_progress; mark completed immediately when done."
    )
    return "\n".join(lines)


def format_todo_reminder() -> str:
    todos = get_todos()
    body = format_todos_for_prompt(todos) if todos else "(no todos yet — create the list with todo_write)"
    return (
        "<reminder>\n"
        "Update your session todos with todo_write. Pass the complete list every time.\n"
        f"Rounds since last todo_write: {rounds_since_todo_update}\n\n"
        f"{body}\n"
        "</reminder>"
    )


def format_todos_welcome_line(todos: list[dict[str, str]] | None = None) -> str | None:
    todos = todos if todos is not None else get_todos()
    if not todos:
        return None
    done = sum(1 for item in todos if item["status"] == "completed")
    active = next((item for item in todos if item["status"] == "in_progress"), None)
    parts = [f"{done}/{len(todos)} done"]
    if active:
        parts.append(f"now: {active['activeForm']}")
    return "  ·  ".join(parts)
