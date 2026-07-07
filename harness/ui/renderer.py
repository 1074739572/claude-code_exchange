"""Unified terminal rendering (Rich) with plain-text fallback."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager

from harness import terminal_state
from harness.ui import theme

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    _RICH = True
except ImportError:
    _RICH = False

_console = Console(highlight=False, legacy_windows=False) if _RICH else None


def _tool_input_preview(tool_input: dict | None, limit: int = 120) -> str:
    if not tool_input:
        return ""
    try:
        text = json.dumps(tool_input, ensure_ascii=False)
    except TypeError:
        text = str(tool_input)
    if len(text) > limit:
        return text[:limit] + "…"
    return text


class Renderer:
    """Single entry for CLI output; keeps loop/llm/cli free of ad-hoc prints."""

    def _write(self, text: str, *, style: str | None = None, end: str = "\n") -> None:
        if not _RICH or _console is None:
            print(text, end=end, flush=True)
            return
        if threading.current_thread() is threading.main_thread() or not terminal_state.CLI_ACTIVE:
            _console.print(text, style=style, end=end)
            return
        line = ""
        if terminal_state.READLINE_AVAILABLE:
            try:
                import readline

                line = readline.get_line_buffer()
            except Exception:
                line = ""
        plain = Text(str(text), style=style or "")
        with _console.capture() as capture:
            _console.print(plain, end=end)
        rendered = capture.get()
        print(f"\r\033[K{rendered}", end="")
        print(theme.PROMPT + line, end="", flush=True)

    def info(self, message: str) -> None:
        self._write(message, style=theme.INFO)

    def muted(self, message: str) -> None:
        self._write(message, style=theme.MUTED)

    def warn(self, message: str) -> None:
        self._write(message, style=theme.WARN)

    def error(self, message: str) -> None:
        self._write(message, style=theme.ERROR)

    def hook(self, label: str, detail: str = "") -> None:
        suffix = f"  {detail}" if detail else ""
        self._write(f"[hook] {label}{suffix}", style=theme.HOOK)

    def user(self, text: str) -> None:
        if _RICH:
            self._write("")
            self._write(f"{theme.PROMPT}{text}", style=theme.USER)
        else:
            self._write(f"\n{theme.PROMPT}{text}")

    def assistant(self, text: str) -> None:
        if not text:
            return
        if _RICH and _console is not None:
            self._write("")
            _console.print(Panel(text, title="Assistant", border_style=theme.ACCENT, padding=(0, 1)))
        else:
            self._write(f"\n{text}")

    def tool_start(self, name: str, tool_input: dict | None = None) -> None:
        preview = _tool_input_preview(tool_input)
        if _RICH and _console is not None:
            body = preview if preview else "running…"
            _console.print(Panel(body, title=f"⚙ {name}", border_style=theme.TOOL, padding=(0, 1)))
        else:
            line = f"> {name}"
            if preview:
                line += f"  {preview}"
            self._write(line, style=theme.TOOL)

    def tool_result(self, preview: str, limit: int = 280) -> None:
        text = preview if len(preview) <= limit else preview[:limit] + "…"
        self._write(text, style=theme.MUTED)

    def plain(self, message: str) -> None:
        self._write(message)

    def todo_checklist(self, todos: list[dict[str, str]]) -> None:
        if not todos:
            return
        if _RICH and _console is not None:
            from harness.ui.todos import render_todo_checklist

            render_todo_checklist(todos, console=_console)
            return
        from harness.ui.todos import _plain_checklist

        self._write(_plain_checklist(todos))

    @contextmanager
    def llm_busy(self, model_tag: str):
        label = f"Thinking  {model_tag}"
        if _RICH and _console is not None:
            with _console.status(f"[{theme.ACCENT}]{label}[/{theme.ACCENT}]", spinner="dots"):
                yield
        else:
            self.muted(f"[llm] {model_tag}")
            yield


renderer = Renderer()
