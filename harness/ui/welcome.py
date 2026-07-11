"""Startup welcome screen (Codex/Cursor-style terminal header)."""

from __future__ import annotations

from harness.models import format_model_status, get_model, model_label
from harness.project.session_store import session_stats
from harness.project.resume import show_project_in_welcome
from harness.project.state import load_state, sync_chapters_from_disk
from harness.providers.config import load_providers, provider_key_status
from harness.settings import WORKDIR
from harness.ui import theme
from harness.ui.banner import TAGLINE, print_hero
from harness.modes import format_mode_status, get_current_mode_profile, get_mode
from harness.usage import format_usage_welcome_line
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
    if not show_project_in_welcome():
        return None
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
    return (
        "/model  /mode  /usage  /undo  /resume  /clear  /banner  /help"
        "  ·  Esc/Ctrl+C rollback  ·  q exit"
    )


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
    usage_line = format_usage_welcome_line()
    mode_line = format_mode_status()
    mode_profile = get_current_mode_profile()
    mode_short = mode_profile.label if mode_profile else get_mode()

    if not _RICH:
        print()
        print("  (:  HELLO AGENT  :)")
        print(f"  {TAGLINE}")
        print()
        print(format_model_status())
        print(mode_line)
        if ready:
            print(f"Providers: {', '.join(ready)}")
        print(f"cwd: {WORKDIR}")
        if stats["exists"]:
            print(f"会话：{stats['active_messages']} 条消息")
        if session_source:
            print(f"已恢复：{session_source}")
        if tasks_line:
            print(f"任务：{tasks_line}")
        if usage_line:
            print(f"用量：{usage_line}")
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
    table.add_row("Mode", f"[bold]{mode_short}[/] [dim](/mode)[/]")
    if ready:
        table.add_row("Providers", ", ".join(ready))
    table.add_row("Workspace", str(WORKDIR))
    if stats["exists"]:
        session_bits = f"{stats['active_messages']} 条消息"
        if stats["compact_boundaries"]:
            session_bits += f"，{stats['compact_boundaries']} 次压缩"
        table.add_row("Session", session_bits)
    if session_source:
        table.add_row("已恢复", session_source)
    if tasks_line:
        table.add_row("Tasks", tasks_line)
    if usage_line:
        table.add_row("Usage", usage_line)
    if project_line:
        table.add_row("Project", project_line)

    table.add_row("Commands", _commands_hint())

    console.print(
        Panel(
            table,
            title="会话",
            border_style=theme.ACCENT,
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    console.print()
