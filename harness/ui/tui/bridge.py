"""Thread-safe bridge between agent_loop worker and Textual UI."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from textual.app import App


class TuiBridge:
    """Push UI events from worker threads; block for Allow? via Modal."""

    def __init__(self) -> None:
        self.app: App | None = None
        self._lock = threading.Lock()

    def bind(self, app: App) -> None:
        self.app = app

    def unbind(self) -> None:
        self.app = None

    def _call(self, method: str, *args: Any) -> None:
        app = self.app
        if app is None:
            return
        fn = getattr(app, method, None)
        if fn is None:
            return
        try:
            app.call_from_thread(fn, *args)
        except Exception:
            pass

    def reset_turn(self, user_query: str = "", model: str = "") -> None:
        self._call("tui_reset_turn", user_query, model)

    def push_step(self, line: str) -> None:
        if not (line or "").strip():
            return
        self._call("tui_append_step", line)

    def push_final(self, text: str) -> None:
        if not (text or "").strip():
            return
        self._call("tui_set_answer", text)

    def push_status(self, text: str) -> None:
        self._call("tui_set_status", text)

    def push_warn(self, text: str) -> None:
        self._call("tui_append_step", f"⚠ {text}")

    def set_busy(self, busy: bool) -> None:
        self._call("tui_set_busy", busy)

    def refresh_usage(self) -> None:
        self._call("refresh_usage_bar")

    def trim_turn_bubbles(self) -> None:
        """U1: remove in-flight turn widgets from Chat."""
        self._call("tui_trim_turn_bubbles")

    def seal_turn_bubbles(self) -> None:
        """Mark live turn bubbles as permanent history."""
        self._call("tui_seal_turn_bubbles")

    def ask_allow(self, detail: str, *, title: str = "Allow destructive command?") -> bool | None:
        """Block worker until Modal dismisses. Returns True/False/None(cancel)."""
        app = self.app
        if app is None:
            return False

        done = threading.Event()
        box: dict[str, bool | None] = {"value": None}

        def _on_dismiss(value: bool | None) -> None:
            box["value"] = value
            done.set()

        def _show() -> None:
            from harness.ui.tui.screens import AllowModal

            app.push_screen(AllowModal(title=title, detail=detail), _on_dismiss)

        try:
            app.call_from_thread(_show)
        except Exception:
            return False
        done.wait(timeout=600)
        return box["value"]


BRIDGE = TuiBridge()
