"""CLI query input with optional redo after interrupt."""

from __future__ import annotations

from harness.models import get_model
from harness.terminal_state import READLINE_AVAILABLE


def format_cli_prompt() -> str:
    """Prompt that shows the active model (Claude Code status-line idea, lightweight)."""
    model = get_model()
    # ASCII-safe for Windows GBK consoles; keep cyan like CLI_PROMPT.
    return f"\033[36m[{model}] > \033[0m"


def read_cli_query(*, redo: str | None = None, prompt: str | None = None) -> str:
    """
    Read the next user query.

    When ``redo`` is set (after Esc/Ctrl+C), pre-fill the line when readline is
    available; otherwise empty Enter resends the previous text.
    """
    active_prompt = prompt if prompt is not None else format_cli_prompt()
    if not redo:
        return input(active_prompt)

    if READLINE_AVAILABLE:
        import readline

        def _prefill() -> None:
            readline.insert_text(redo)

        readline.set_startup_hook(_prefill)
        try:
            line = input(active_prompt)
        finally:
            readline.set_startup_hook()
        return line if line.strip() else redo

    print(f"\n  (previous question — press Enter to resend, or type a new one)\n  {redo}\n")
    line = input(active_prompt)
    return line if line.strip() else redo
