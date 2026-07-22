"""Hard-reset terminal modes left behind by a crashed Textual session.

When Textual dies without cleanup, the host terminal often stays in mouse
reporting / alternate-screen mode. Restarting `python main.py` in that same
tab then looks like an instant crash (raw ``^[[<…M`` mouse dumps).
"""

from __future__ import annotations

import sys

# Disable common mouse / focus / bracketed-paste / alt-screen modes Textual uses.
_RESET_SEQ = (
    "\033[?1000l"  # X10 mouse
    "\033[?1002l"  # cell motion
    "\033[?1003l"  # all motion
    "\033[?1005l"  # utf-8 mouse
    "\033[?1006l"  # SGR mouse (what prints as ^[[<r;c;M)
    "\033[?1015l"  # urxvt mouse
    "\033[?1016l"  # SGR pixels
    "\033[?1004l"  # focus events
    "\033[?2004l"  # bracketed paste
    "\033[?1049l"  # leave alternate screen
    "\033[?25h"  # show cursor
    "\033[0m"  # reset SGR
    "\033[?7h"  # wraparound on
)


def reset_terminal_modes(*, stream=None) -> None:
    """Best-effort restore of a polluted interactive terminal."""
    out = stream if stream is not None else sys.stdout
    try:
        if hasattr(out, "isatty") and not out.isatty():
            return
    except Exception:
        return
    try:
        out.write(_RESET_SEQ)
        out.flush()
    except Exception:
        pass
