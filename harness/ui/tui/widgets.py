"""Clickable meta chips under the chat pane."""

from __future__ import annotations

from textual.widgets import Collapsible, Static

from harness.ui.tui.events import ToolEvent


_TOOL_ICONS = {
    "running": "●",
    "ok": "✓",
    "failed": "✗",
    "blocked": "⊘",
    "repeat": "↻",
}


class ToolCard(Collapsible):
    """A compact tool call whose status can be updated in place."""

    def __init__(self, event: ToolEvent, *, live: bool = True) -> None:
        self.tool_use_id = event.tool_use_id
        self.signature = (event.name, event.summary)
        self._detail = Static("", classes="tool-card-detail", markup=False)
        classes = "tool-card"
        if live:
            classes += " turn-live"
        super().__init__(
            self._detail,
            title=self._title_for(event),
            collapsed=True,
            classes=classes,
        )
        self.update_event(event)

    @staticmethod
    def _title_for(event: ToolEvent) -> str:
        icon = _TOOL_ICONS.get(event.phase, "●")
        summary = f"  {event.summary}" if event.summary else ""
        repeat = f"  ×{event.streak}" if event.streak > 1 else ""
        return f"{icon} {event.name}{summary}{repeat}"

    def update_event(self, event: ToolEvent) -> None:
        self.title = self._title_for(event)
        for phase in _TOOL_ICONS:
            self.remove_class(f"tool-{phase}")
        self.add_class(f"tool-{event.phase}")
        detail = event.preview.strip()
        if not detail:
            if event.phase == "running":
                detail = "Running…"
            elif event.phase == "ok":
                detail = "Completed"
            elif event.phase == "blocked":
                detail = "Blocked by guard or permission policy"
        self._detail.update(detail)


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
