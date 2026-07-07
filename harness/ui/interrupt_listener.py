"""Listen for Esc / Ctrl+C while the agent loop is running."""

from __future__ import annotations

import signal
import sys
import threading
import time


class InterruptListener:
    """Background poll for Esc or Ctrl+C during a blocking agent turn."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._old_sigint = None
        self._last_fire = 0.0

    def start(self, on_interrupt) -> None:
        self._stop.clear()
        self._last_fire = 0.0

        def fire() -> None:
            now = time.monotonic()
            if now - self._last_fire < 0.35:
                return
            self._last_fire = now
            on_interrupt()

        if sys.stdin.isatty():

            def run() -> None:
                while not self._stop.is_set():
                    if _poll_key_interrupt():
                        fire()
                        return
                    time.sleep(0.04)

            self._thread = threading.Thread(target=run, daemon=True)
            self._thread.start()

        def _sigint_handler(signum, frame) -> None:  # noqa: ARG001
            fire()

        try:
            self._old_sigint = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, _sigint_handler)
        except (ValueError, OSError):
            # Not the main thread or platform without SIGINT in this context.
            self._old_sigint = None

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.2)
            self._thread = None
        if self._old_sigint is not None:
            try:
                signal.signal(signal.SIGINT, self._old_sigint)
            except (ValueError, OSError):
                pass
            self._old_sigint = None


def _poll_key_interrupt() -> bool:
    if sys.platform == "win32":
        return _poll_interrupt_windows()
    return _poll_interrupt_unix()


def _poll_interrupt_windows() -> bool:
    import msvcrt

    if not msvcrt.kbhit():
        return False
    ch = msvcrt.getch()
    if ch == b"\x03":
        return True
    if ch == b"\x1b":
        return True
    return False


def _poll_interrupt_unix() -> bool:
    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return False
        ch = sys.stdin.read(1)
        return ch in ("\x03", "\x1b")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
