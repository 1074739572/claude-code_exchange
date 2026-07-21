"""TUI mode flags (Textual vs classic Rich CLI)."""

from __future__ import annotations

import os
import threading

_lock = threading.Lock()
_tui_active = False
_tui_shutdown = False


def is_tui_active() -> bool:
    with _lock:
        return _tui_active


def set_tui_active(active: bool) -> None:
    global _tui_active
    with _lock:
        _tui_active = bool(active)
        if active:
            # New session clears prior shutdown swallow.
            global _tui_shutdown
            _tui_shutdown = False


def begin_tui_shutdown() -> None:
    """Exit in progress: swallow console writes so worker cannot leak to terminal."""
    global _tui_shutdown
    with _lock:
        _tui_shutdown = True


def is_tui_shutdown() -> bool:
    with _lock:
        return _tui_shutdown


def clear_tui_shutdown() -> None:
    global _tui_shutdown
    with _lock:
        _tui_shutdown = False


def prefer_tui() -> bool:
    """Default on; HARNESS_TUI=0/classic/off disables Textual entry."""
    raw = os.getenv("HARNESS_TUI", "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "classic")
