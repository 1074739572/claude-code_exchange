"""Textual TUI entry (default agent chrome)."""

from __future__ import annotations

from harness.ui.tui.mode import prefer_tui, is_tui_active, set_tui_active

__all__ = [
    "run_tui",
    "prefer_tui",
    "is_tui_active",
    "set_tui_active",
]


def run_tui() -> None:
    """Boot Textual app with the same session bootstrap as classic CLI."""
    try:
        import textual  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "textual is required for the TUI. Install with: pip install textual\n"
            "Or run classic CLI: python main.py --classic"
        ) from exc

    from harness.cli import bootstrap_cli_session
    from harness.models import get_model, model_label
    from harness.ui.tui.app import HarnessApp
    from harness.ui.tui.mode import begin_tui_shutdown, clear_tui_shutdown, set_tui_active

    history, context = bootstrap_cli_session(
        welcome=False,
        start_cron=True,
        cli_active=False,
    )
    app = HarnessApp(history, context, model_name=model_label(get_model()))
    try:
        set_tui_active(True)
        app.run()
    finally:
        begin_tui_shutdown()
        set_tui_active(False)
        clear_tui_shutdown()
