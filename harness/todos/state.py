"""In-memory session todos with optional persistence to .project/todos.json."""

from __future__ import annotations

import ast
import json
import re
from typing import Any

from harness.settings import PROJECT_DIR

TODOS_PATH = PROJECT_DIR / "todos.json"

_CURRENT: list[dict[str, str]] = []
rounds_since_todo_update: int = 0


def get_todos() -> list[dict[str, str]]:
    return list(_CURRENT)


def _derive_active_form(content: str, status: str) -> str:
    text = content.strip().rstrip(".")
    if status == "in_progress":
        if text.endswith("…") or text.endswith("..."):
            return text
        words = text.split()
        if words:
            first = words[0]
            if re.match(r"^(run|fix|add|update|write|read|test|check|implement|create|refactor)\b", first, re.I):
                return f"{first[0].upper()}{first[1:]}…" if len(first) > 1 else f"{first}…"
        return f"{text}…"
    return text


def normalize_todos(raw: Any) -> tuple[list[dict[str, str]] | None, str | None]:
    todos = raw
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

    normalized: list[dict[str, str]] = []
    for index, todo in enumerate(todos):
        if not isinstance(todo, dict):
            return None, f"Error: todos[{index}] must be an object"
        content = todo.get("content")
        status = todo.get("status")
        if not content or not status:
            return None, f"Error: todos[{index}] missing 'content' or 'status'"
        if status not in ("pending", "in_progress", "completed"):
            return (
                None,
                f"Error: todos[{index}] has invalid status '{status}' "
                "(use pending, in_progress, or completed)",
            )
        active_form = (todo.get("activeForm") or todo.get("active_form") or "").strip()
        if not active_form:
            active_form = _derive_active_form(str(content), status)
        normalized.append(
            {
                "content": str(content).strip(),
                "activeForm": active_form,
                "status": status,
            }
        )

    in_progress = [item for item in normalized if item["status"] == "in_progress"]
    if len(in_progress) > 1:
        titles = ", ".join(f'"{item["content"][:40]}"' for item in in_progress)
        return (
            None,
            f"Error: only one todo may be in_progress at a time (found {len(in_progress)}: {titles})",
        )
    return normalized, None


def set_todos(todos: list[dict[str, str]]) -> None:
    global _CURRENT, rounds_since_todo_update
    _CURRENT = todos
    rounds_since_todo_update = 0
    _persist()


def write_todos(raw: Any) -> tuple[list[dict[str, str]] | None, str | None]:
    todos, error = normalize_todos(raw)
    if error:
        return None, error
    set_todos(todos)
    return todos, None


def clear_todos() -> None:
    global _CURRENT, rounds_since_todo_update
    _CURRENT = []
    rounds_since_todo_update = 0
    if TODOS_PATH.exists():
        TODOS_PATH.unlink()


def load_todos_from_disk() -> list[dict[str, str]]:
    global _CURRENT
    if not TODOS_PATH.exists():
        _CURRENT = []
        return []
    try:
        raw = json.loads(TODOS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _CURRENT = []
        return []
    todos, error = normalize_todos(raw)
    if error or todos is None:
        _CURRENT = []
        return []
    _CURRENT = todos
    return list(_CURRENT)


def note_llm_round_without_todo_update() -> None:
    global rounds_since_todo_update
    rounds_since_todo_update += 1


def _persist() -> None:
    if not _CURRENT:
        if TODOS_PATH.exists():
            TODOS_PATH.unlink()
        return
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    TODOS_PATH.write_text(
        json.dumps(_CURRENT, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
