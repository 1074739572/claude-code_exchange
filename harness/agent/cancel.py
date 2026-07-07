"""Cooperative cancel for in-flight agent turns (Esc / Ctrl+C)."""

from __future__ import annotations

import threading

_lock = threading.Lock()
_cancel_requested = False


def clear_cancel() -> None:
    global _cancel_requested
    with _lock:
        _cancel_requested = False


def request_cancel() -> None:
    global _cancel_requested
    with _lock:
        _cancel_requested = True


def is_cancelled() -> bool:
    with _lock:
        return _cancel_requested
