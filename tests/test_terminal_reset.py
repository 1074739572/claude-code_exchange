"""Tests for terminal mode reset helper."""

from __future__ import annotations

from io import StringIO
from unittest import mock

from harness.ui.tui.terminal_reset import reset_terminal_modes


def test_reset_writes_mouse_disable_sequences() -> None:
    buf = StringIO()
    buf.isatty = lambda: True  # type: ignore[method-assign]
    reset_terminal_modes(stream=buf)
    out = buf.getvalue()
    assert "\033[?1006l" in out  # SGR mouse off
    assert "\033[?1000l" in out
    assert "\033[?1049l" in out  # leave alt screen
    assert "\033[?25h" in out  # cursor on


def test_reset_skips_non_tty() -> None:
    buf = StringIO()
    buf.isatty = lambda: False  # type: ignore[method-assign]
    reset_terminal_modes(stream=buf)
    assert buf.getvalue() == ""


def test_reset_swallows_write_errors() -> None:
    class Boom:
        def isatty(self) -> bool:
            return True

        def write(self, _data: str) -> int:
            raise OSError("closed")

        def flush(self) -> None:
            raise OSError("closed")

    reset_terminal_modes(stream=Boom())  # must not raise
