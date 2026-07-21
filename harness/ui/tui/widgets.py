"""Clickable meta chips under the chat pane."""

from __future__ import annotations

from textual.widgets import Static


class MetaChip(Static):
    """Clickable status chip (model / mode)."""

    DEFAULT_CSS = """
    MetaChip {
        width: auto;
        height: 1;
        padding: 0 1;
        margin: 0 1 0 0;
    }
    MetaChip:hover {
        text-style: bold underline;
    }
    """

    def __init__(self, renderable: str = "", *, chip: str = "", **kwargs) -> None:
        super().__init__(renderable, **kwargs)
        self.chip = chip

    def on_click(self) -> None:
        app = self.app
        if self.chip == "model" and hasattr(app, "action_pick_model"):
            app.action_pick_model()
        elif self.chip == "mode" and hasattr(app, "action_pick_mode"):
            app.action_pick_mode()
