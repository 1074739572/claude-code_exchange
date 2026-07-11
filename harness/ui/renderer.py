"""Unified terminal rendering (Rich) with plain-text fallback."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager

from harness import terminal_state
from harness.ui import theme
from harness.ui.tool_display import (
    hooks_verbose,
    summarize_tool_input,
    summarize_tool_output,
    tool_ui_mode,
)

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
        if not hooks_verbose():
            return
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
            _console.print(
                Panel(text, title="Assistant", border_style=theme.ACCENT, padding=(0, 1))
            )
        else:
            self._write(f"\n{text}")

    def tool_intent(self, text: str) -> None:
        """Show model's short rationale before a tool call (not a full answer panel)."""
        mode = tool_ui_mode()
        if mode == "off" or not (text or "").strip():
            return
        # Keep to a few lines so narration doesn't become another dump.
        lines = [ln.rstrip() for ln in text.strip().splitlines() if ln.strip()]
        preview = " ".join(lines)
        if len(preview) > 220:
            preview = preview[:219] + "…"
        self._write(f"› {preview}", style=theme.MUTED)

    def tool_start(self, name: str, tool_input: dict | None = None) -> None:
        mode = tool_ui_mode()
        if mode == "off":
            return
        summary = summarize_tool_input(name, tool_input)
        if mode == "verbose":
            preview = _tool_input_preview(tool_input)
            if _RICH and _console is not None:
                body = preview if preview else "running…"
                _console.print(
                    Panel(
                        body,
                        title=f"⚙ {name}",
                        border_style=theme.TOOL,
                        padding=(0, 1),
                    )
                )
            else:
                line = f"> {name}"
                if preview:
                    line += f"  {preview}"
                self._write(line, style=theme.TOOL)
            return
        detail = f"  {summary}" if summary else ""
        self._write(f"● {name}{detail}", style=theme.TOOL)

    def tool_repeat(
        self,
        name: str,
        tool_input: dict | None,
        *,
        streak: int,
        blocked: bool = False,
    ) -> None:
        """Collapse identical consecutive calls instead of reprinting full lines."""
        mode = tool_ui_mode()
        if mode == "off":
            return
        summary = summarize_tool_input(name, tool_input)
        detail = f"  {summary}" if summary else ""
        if blocked:
            self._write(
                f"⊘ {name}{detail}  (×{streak} identical — blocked)",
                style=theme.WARN,
            )
        else:
            self._write(
                f"↻ {name}{detail}  (×{streak} identical)",
                style=theme.MUTED,
            )

    def tool_result(
        self,
        preview: str,
        limit: int = 280,
        *,
        name: str | None = None,
        tool_input: dict | None = None,
    ) -> None:
        mode = tool_ui_mode()
        if mode == "off":
            return
        if mode == "verbose" or not name:
            text = preview if len(preview) <= limit else preview[:limit] + "…"
            self._write(text, style=theme.MUTED)
            return
        # Don't dump full result again for repeat-guard blocks — one line is enough
        if str(preview).startswith("[RepeatGuard]"):
            self._write("  → blocked duplicate call", style=theme.WARN)
            return
        summary = summarize_tool_output(name, preview, tool_input=tool_input)
        self._write(f"  → {summary}", style=theme.MUTED)

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
