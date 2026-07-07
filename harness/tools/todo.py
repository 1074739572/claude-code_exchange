"""Session todo_write tool handler."""

from __future__ import annotations

from harness.todos.format import format_todos_tool_result
from harness.todos.state import write_todos
from harness.ui.renderer import renderer


def run_todo_write(todos: list) -> str:
    updated, error = write_todos(todos)
    if error:
        return error
    assert updated is not None

    renderer.todo_checklist(updated)
    return format_todos_tool_result(updated)
