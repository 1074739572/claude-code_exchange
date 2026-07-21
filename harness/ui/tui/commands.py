"""Slash-command handlers for the Textual TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from harness.ui.tui.app import HarnessApp


def _match(query: str, command: str) -> bool:
    text = query.strip().lower()
    command = command.lower()
    return text == command or text.startswith(command + " ")


def dispatch_slash(app: HarnessApp, query: str) -> bool:
    """Handle a slash/meta command. Returns True if consumed."""
    q = query.strip()
    if not q:
        return False

    if q.lower() in ("/exit", "/quit", "exit", "quit", "q"):
        app.exit()
        return True

    if q.lower() == "/classic":
        app.tui_set_status("Restart with: python main.py --classic")
        app.chat_append(
            "system",
            "Classic Rich CLI: python main.py --classic",
        )
        return True

    if _match(q, "/help") or q.lower() == "help":
        app.chat_append("assistant", _help_md())
        app.tui_set_status("Help")
        return True

    if _match(q, "/model"):
        _handle_model(app, q)
        return True

    if _match(q, "/mode"):
        _handle_mode(app, q)
        return True

    if q.startswith("/"):
        app.chat_append(
            "system",
            f"`{q}` not in TUI yet. Built-in: /model /mode /help /classic /quit. "
            "Or: python main.py --classic",
        )
        app.tui_set_status("Unknown command")
        return True

    return False


def _help_md() -> str:
    return """# Commands (TUI)

| Command | Action |
|---------|--------|
| `/model` | Pick model (or click 🤖 below chat) |
| `/model <id>` | Switch by id |
| `/mode` | Pick mode (or click 🧭) |
| `/mode <id>` | Switch mode |
| `/help` | This help |
| `/classic` | Rich CLI hint |
| `/quit` | Exit |

**Layout:** top = usage · middle = chat history · under chat = model/mode/status · bottom = input
"""


def _handle_model(app: HarnessApp, query: str) -> None:
    from harness.models import get_model, model_label, set_model
    from harness.ui.model_picker import menu_entries

    parts = query.strip().split(maxsplit=1)
    if len(parts) > 1 and parts[1].lower() not in ("list", "pick", "picker"):
        msg = set_model(parts[1])
        app.refresh_meta_bar()
        app.tui_set_status(msg)
        app.chat_append("step", f"model → {model_label()}")
        return

    labels, model_ids, cursor = menu_entries()
    if not model_ids:
        app.tui_set_status("No models in config/models.json")
        return

    def on_pick(model_id: str | None) -> None:
        if not model_id:
            app.tui_set_status(f"Kept model: {get_model()}")
            return
        msg = set_model(model_id)
        app.refresh_meta_bar()
        app.chat_append("step", f"model → {model_label()}")
        app.tui_set_status(msg)

    app.open_inline_picker(
        "Select model",
        labels,
        model_ids,
        initial_index=cursor,
        on_pick=on_pick,
    )


def _handle_mode(app: HarnessApp, query: str) -> None:
    from harness.modes import format_mode_status, get_mode, set_mode
    from harness.modes.registry import format_mode_catalog
    from harness.ui.mode_picker import menu_entries

    parts = query.strip().split(maxsplit=1)
    if len(parts) > 1:
        arg = parts[1].strip()
        if arg.lower() == "help":
            app.chat_append("assistant", format_mode_catalog())
            return
        if arg.lower() not in ("list", "pick", "picker"):
            msg = set_mode(arg)
            app.refresh_meta_bar()
            app.chat_append("step", f"mode → {get_mode()}")
            app.tui_set_status(msg)
            return

    labels, mode_ids, cursor = menu_entries()
    if not mode_ids:
        app.tui_set_status("No modes in config/modes.json")
        return

    def on_pick(mode_id: str | None) -> None:
        if not mode_id:
            app.tui_set_status(format_mode_status())
            return
        msg = set_mode(mode_id)
        app.refresh_meta_bar()
        app.chat_append("step", f"mode → {get_mode()}")
        app.tui_set_status(msg)

    app.open_inline_picker(
        "Select mode",
        labels,
        mode_ids,
        initial_index=cursor,
        on_pick=on_pick,
    )
