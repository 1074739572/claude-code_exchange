"""Cross-platform arrow-key menu (Windows + Unix TTY)."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable

try:
    from rich.console import Console
    from rich.live import Live
    from rich.text import Text

    _RICH = True
except ImportError:
    _RICH = False


def is_interactive_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def drain_stdin() -> None:
    """Drop pending keypresses (e.g. Enter after /model)."""
    if sys.platform == "win32":
        import msvcrt

        while msvcrt.kbhit():
            msvcrt.getch()
        return
    import select

    while select.select([sys.stdin], [], [], 0)[0]:
        sys.stdin.read(1)


def _read_key_windows() -> str:
    import msvcrt

    while True:
        if not msvcrt.kbhit():
            time.sleep(0.02)
            continue
        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0") and msvcrt.kbhit():
            code = msvcrt.getch()
            if code == b"H":
                return "up"
            if code == b"P":
                return "down"
            continue
        if ch in (b"\r", b"\n"):
            return "enter"
        if ch == b"\x03":
            raise KeyboardInterrupt
        if ch == b"\x1b":
            if msvcrt.kbhit() and msvcrt.getch() == b"[" and msvcrt.kbhit():
                arrow = msvcrt.getch()
                if arrow == b"A":
                    return "up"
                if arrow == b"B":
                    return "down"
            return "esc"


def _read_key_unix() -> str:
    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch1 = sys.stdin.read(1)
            if ch1 == "\x03":
                raise KeyboardInterrupt
            if ch1 in ("\r", "\n"):
                return "enter"
            if ch1 == "\x1b":
                if select.select([sys.stdin], [], [], 0.05)[0]:
                    ch2 = sys.stdin.read(1)
                    if ch2 == "[" and select.select([sys.stdin], [], [], 0.05)[0]:
                        ch3 = sys.stdin.read(1)
                        if ch3 == "A":
                            return "up"
                        if ch3 == "B":
                            return "down"
                return "esc"
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return "esc"


def read_menu_key() -> str:
    if sys.platform == "win32":
        return _read_key_windows()
    return _read_key_unix()


def render_menu(
    items: list[str],
    *,
    index: int,
    title: str,
    hint: str = "↑↓ move · Enter confirm · Esc cancel",
) -> Text:
    body = Text()
    body.append(f"{title}\n", style="bold")
    for row, item in enumerate(items):
        selected = row == index
        body.append("  › " if selected else "    ", style="bold cyan" if selected else "")
        body.append(item, style="bold cyan" if selected else "dim")
        body.append("\n")
    body.append(f"\n{hint}", style="dim")
    return body


def select_from_list(
    items: list[str],
    *,
    title: str = "Select",
    initial_index: int = 0,
    hint: str = "↑↓ move · Enter confirm · Esc cancel",
) -> int | None:
    """Return selected index, or None if cancelled."""
    if not items:
        return None
    if not is_interactive_tty():
        return None

    index = max(0, min(initial_index, len(items) - 1))
    drain_stdin()

    if not _RICH:
        print(title)
        for row, item in enumerate(items):
            mark = ">" if row == index else " "
            print(f"{mark} {item}")
        print(hint)
        while True:
            key = read_menu_key()
            if key == "up":
                index = (index - 1) % len(items)
                print(f"> {items[index]}")
            elif key == "down":
                index = (index + 1) % len(items)
                print(f"> {items[index]}")
            elif key == "enter":
                return index
            elif key == "esc":
                return None

    console = Console(highlight=False, legacy_windows=False)
    with Live(
        render_menu(items, index=index, title=title, hint=hint),
        console=console,
        refresh_per_second=12,
        transient=True,
    ) as live:
        while True:
            key = read_menu_key()
            if key == "up":
                index = (index - 1) % len(items)
            elif key == "down":
                index = (index + 1) % len(items)
            elif key == "enter":
                return index
            elif key == "esc":
                return None
            live.update(render_menu(items, index=index, title=title, hint=hint))


def select_with_mapper(
    items: list[str],
    *,
    title: str,
    initial_index: int = 0,
    on_select: Callable[[int], str],
    on_cancel: Callable[[], str],
) -> str:
    choice = select_from_list(items, title=title, initial_index=initial_index)
    if choice is None:
        return on_cancel()
    return on_select(choice)
