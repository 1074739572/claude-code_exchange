"""CLI query input with optional redo after interrupt."""

from __future__ import annotations

from harness.settings import CLI_PROMPT
from harness.terminal_state import READLINE_AVAILABLE


def read_cli_query(*, redo: str | None = None, prompt: str = CLI_PROMPT) -> str:
    """
    Read the next user query.

    When ``redo`` is set (after Esc/Ctrl+C), pre-fill the line when readline is
    available; otherwise empty Enter resends the previous text.
    """
    if not redo:
        return input(prompt)

    if READLINE_AVAILABLE:
        import readline

        def _prefill() -> None:
            readline.insert_text(redo)

        readline.set_startup_hook(_prefill)
        try:
            line = input(prompt)
        finally:
            readline.set_startup_hook()
        return line if line.strip() else redo

    print(f"\n  (previous question — press Enter to resend, or type a new one)\n  {redo}\n")
    line = input(prompt)
    return line if line.strip() else redo
