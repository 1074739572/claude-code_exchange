"""Terminal output helpers for CLI and background threads."""

from __future__ import annotations

import threading

from harness.settings import CLI_PROMPT

try:
    import readline

    readline.parse_and_bind("set bind-tty-special-chars off")
    READLINE_AVAILABLE = True
except ImportError:
    READLINE_AVAILABLE = False

CLI_ACTIVE = False


def terminal_print(text: str) -> None:
    if threading.current_thread() is threading.main_thread() or not CLI_ACTIVE:
        print(text)
        return
    line = ""
    if READLINE_AVAILABLE:
        try:
            line = readline.get_line_buffer()
        except Exception:
            line = ""
    print(f"\r\033[K{text}")
    print(CLI_PROMPT + line, end="", flush=True)
