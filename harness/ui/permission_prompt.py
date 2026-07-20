"""Cancel-aware Allow? [y/N] prompts (Esc / Ctrl+C must not leave input() stuck)."""

from __future__ import annotations

import sys
import time

from harness.agent.cancel import is_cancelled, request_cancel
from harness.ui.interrupt_listener import pause_key_poll, resume_key_poll


def ask_allow(prompt: str = "  Allow? [y/N] ") -> bool | None:
    """Ask y/N without blocking forever under Esc/Ctrl+C.

    Returns:
        True  — allow
        False — deny (n / Enter / default)
        None  — cancelled (Esc, Ctrl+C, or cooperative cancel flag)
    """
    print(prompt, end="", flush=True)
    pause_key_poll()
    try:
        if sys.stdin.isatty() and sys.platform == "win32":
            return _ask_windows()
        if sys.stdin.isatty():
            return _ask_unix()
        # Non-TTY (piped): fall back to one-shot line read; still honor cancel.
        if is_cancelled():
            print()
            return None
        line = sys.stdin.readline()
        if is_cancelled():
            print()
            return None
        choice = (line or "").strip().lower()
        return choice in ("y", "yes")
    finally:
        resume_key_poll()


def _ask_windows() -> bool | None:
    import msvcrt

    while True:
        if is_cancelled():
            print()
            return None
        if not msvcrt.kbhit():
            time.sleep(0.04)
            continue
        ch = msvcrt.getch()
        # Arrow / function keys are two-byte sequences; discard the rest.
        if ch in (b"\x00", b"\xe0"):
            if msvcrt.kbhit():
                msvcrt.getch()
            continue
        if ch in (b"\x03", b"\x1b"):
            request_cancel()
            print()
            return None
        if ch in (b"y", b"Y"):
            print("y")
            return True
        if ch in (b"n", b"N", b"\r", b"\n"):
            print("n" if ch in (b"n", b"N") else "")
            return False
        # Ignore other keys; keep waiting.


def _ask_unix() -> bool | None:
    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            if is_cancelled():
                print()
                return None
            ready, _, _ = select.select([sys.stdin], [], [], 0.05)
            if not ready:
                continue
            ch = sys.stdin.read(1)
            if ch in ("\x03", "\x1b"):
                request_cancel()
                print()
                return None
            if ch in ("y", "Y"):
                print("y")
                return True
            if ch in ("n", "N", "\r", "\n"):
                print("n" if ch in ("n", "N") else "")
                return False
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
