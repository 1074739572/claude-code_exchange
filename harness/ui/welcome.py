"""Startup welcome screen (Codex/Cursor-style terminal header)."""

from __future__ import annotations

from harness.models import format_model_status, get_model, model_label
from harness.project.session_store import session_stats
from harness.project.state import load_state, sync_chapters_from_disk
from harness.providers.config import load_providers, provider_key_status
from harness.settings import WORKDIR
from harness.ui import theme
from harness.ui.banner import TAGLINE, print_hero
from harness.todos.format import format_todos_welcome_line

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    _RICH = True
except ImportError:
    _RICH = False


def _chapter_line() -> str | None:
    state = load_state()
    if state is None:
        return None
    state = sync_chapters_from_disk(state)
    done = sum(1 for c in state.chapters if c.status == "done")
    total = len(state.chapters)
    current = next((c for c in state.chapters if c.id == state.current_chapter), None)
    cur = f"{current.id} {current.title}" if current else "—"
    return f"{state.title}  ·  {done}/{total} done  ·  current: {cur}"


def _commands_hint() -> str:
    return "/model  /resume  /clear  /import-transcript  /banner  /help  ·  q exit"


def render_welcome(*, session_source: str | None = None) -> None:
    """Print welcome hero + session panel."""
    model_id = get_model()
    label = model_label(model_id)
    ready = [
        load_providers()[pid].label
        for pid, ok in provider_key_status().items()
        if ok
    ]
    stats = session_stats()
    project_line = _chapter_line()
    tasks_line = format_todos_welcome_line()

    if not _RICH:
        print()
        print("  (:  HELLO AGENT  :)")
        print(f"  {TAGLINE}")
        print()
        print(format_model_status())
        if ready:
            print(f"Providers: {', '.join(ready)}")
        print(f"cwd: {WORKDIR}")
        if stats["exists"]:
            print(f"Session: {stats['active_messages']} messages")
        if session_source:
            print(f"Continued: {session_source}")
        if tasks_line:
            print(f"Tasks: {tasks_line}")
        if project_line:
            print(project_line)
        print(_commands_hint())
        print()
        return

    console = Console(highlight=False, legacy_windows=False)
    print_hero(console, style="classic", width=console.size.width)

    table = Table.grid(padding=(0, 2))
    table.add_column(style=theme.MUTED, justify="right")
    table.add_column()

    table.add_row("Model", f"[bold]{label}[/] [dim]({model_id})[/]")
    if ready:
        table.add_row("Providers", ", ".join(ready))
    table.add_row("Workspace", str(WORKDIR))
    if stats["exists"]:
        session_bits = f"{stats['active_messages']} active messages"
        if stats["compact_boundaries"]:
            session_bits += f", {stats['compact_boundaries']} compact(s)"
        table.add_row("Session", session_bits)
    if session_source:
        table.add_row("Continued", session_source)
    if tasks_line:
        table.add_row("Tasks", tasks_line)
    if project_line:
        table.add_row("Project", project_line)

    table.add_row("Commands", _commands_hint())

    console.print(
        Panel(
            table,
            title="Session",
            border_style=theme.ACCENT,
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    console.print()
