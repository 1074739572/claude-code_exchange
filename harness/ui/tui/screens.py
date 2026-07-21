"""Inline picker + permission modal for Textual TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static


class AllowModal(ModalScreen[bool | None]):
    """y = allow, n/Enter = deny, Esc = cancel.

    Permission stays a modal (must block the worker). Model/mode pickers
    live inline under Answer — see HarnessApp.open_inline_picker.
    """

    BINDINGS = [
        Binding("y", "allow", "Allow", show=True),
        Binding("Y", "allow", "Allow", show=False),
        Binding("n", "deny", "Deny", show=True),
        Binding("N", "deny", "Deny", show=False),
        Binding("enter", "deny", "Deny", show=False),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    def __init__(self, title: str, detail: str) -> None:
        super().__init__()
        self._title = title
        self._detail = detail

    def compose(self) -> ComposeResult:
        with Vertical(id="allow-dialog"):
            yield Label(self._title, id="allow-title")
            yield Static(self._detail or "(no detail)", id="allow-detail")
            yield Label("y allow · n deny · Esc cancel", id="allow-hint")

    def action_allow(self) -> None:
        self.dismiss(True)

    def action_deny(self) -> None:
        self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(None)
