"""Shared CLI terminal flags (no renderer/console imports)."""

from __future__ import annotations

CLI_ACTIVE = False

try:
    import readline

    readline.parse_and_bind("set bind-tty-special-chars off")
    READLINE_AVAILABLE = True
except ImportError:
    READLINE_AVAILABLE = False
