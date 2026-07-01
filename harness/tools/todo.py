"""Session todo list tool."""

from __future__ import annotations

import ast
import json

from harness import tasks as task_state


def _normalize_todos(todos):
    if isinstance(todos, str):
        try:
            todos = json.loads(todos)
        except json.JSONDecodeError:
            try:
                todos = ast.literal_eval(todos)
            except (SyntaxError, ValueError):
                return None, "Error: todos must be a list or JSON array string"
    if not isinstance(todos, list):
        return None, "Error: todos must be a list"
    for index, todo in enumerate(todos):
        if not isinstance(todo, dict):
            return None, f"Error: todos[{index}] must be an object"
        if "content" not in todo or "status" not in todo:
            return None, f"Error: todos[{index}] missing 'content' or 'status'"
        if todo["status"] not in ("pending", "in_progress", "completed"):
            return (
                f"Error: todos[{index}] has invalid status '{todo['status']}'"
            )
    return todos, None


def run_todo_write(todos: list) -> str:
    todos, error = _normalize_todos(todos)
    if error:
        return error
    task_state.CURRENT_TODOS = todos
    print(f"  \033[33m[todo] updated {len(task_state.CURRENT_TODOS)} item(s)\033[0m")
    return f"Updated {len(task_state.CURRENT_TODOS)} todos"
