"""Rich checklist for session todos."""

from __future__ import annotations

from harness.ui import theme

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    _RICH = True
except ImportError:
    _RICH = False


def _plain_checklist(todos: list[dict[str, str]]) -> str:
    lines = ["Tasks:"]
    for todo in todos:
        status = todo["status"]
        if status == "completed":
            lines.append(f"  [x] {todo['content']}")
        elif status == "in_progress":
            lines.append(f"  [>] {todo['activeForm']}")
        else:
            lines.append(f"  [ ] {todo['content']}")
    return "\n".join(lines)


def render_todo_checklist(
    todos: list[dict[str, str]],
    *,
    console: Console | None = None,
) -> None:
    if not todos:
        return
    if not _RICH or console is None:
        print(_plain_checklist(todos))
        return

    body = Text()
    for index, todo in enumerate(todos):
        if index:
            body.append("\n")
        status = todo["status"]
        if status == "completed":
            body.append("  [x] ", style="green")
            body.append(todo["content"], style="dim strike")
        elif status == "in_progress":
            body.append("  > ", style=f"bold {theme.ACCENT}")
            body.append(todo["activeForm"], style=f"bold {theme.ACCENT}")
        else:
            body.append("  [ ] ", style=theme.MUTED)
            body.append(todo["content"], style=theme.MUTED)

    console.print(
        Panel(
            body,
            title="Tasks",
            border_style=theme.ACCENT,
            padding=(0, 1),
        )
    )
