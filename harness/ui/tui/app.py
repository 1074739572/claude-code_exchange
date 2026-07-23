"""Textual App: Usage | Chat | Meta | Composer (Send/Stop)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Label, Markdown, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from harness.agent.cancel import request_cancel
from harness.ui.tui.bridge import BRIDGE
from harness.ui.tui.mode import begin_tui_shutdown, set_tui_active
from harness.ui.tui.widgets import MetaChip

_CSS_PATH = Path(__file__).with_name("theme.tcss")
_TURN_LIVE = "turn-live"
_COMPOSER_PLACEHOLDER = (
    "Ask…  Enter send · Shift+Enter newline · Esc stop · Ctrl+Q quit"
)


class ComposerTextArea(TextArea):
    """Chat composer: Enter sends; Shift+Enter inserts a newline."""

    BINDINGS = [
        Binding("enter", "composer_submit", "Send", show=False, priority=True),
        Binding("shift+enter", "composer_newline", "Newline", show=False, priority=True),
    ]

    def action_composer_submit(self) -> None:
        app = self.app
        if hasattr(app, "action_submit_or_stop"):
            app.action_submit_or_stop()  # type: ignore[attr-defined]

    def action_composer_newline(self) -> None:
        self.insert("\n")


class HarnessApp(App[None]):
    """Merged chat TUI with Send/Stop toggle and clean quit (X1/B2/U1)."""

    TITLE = "improved_harness"
    CSS_PATH = _CSS_PATH
    BINDINGS = [
        Binding("escape", "interrupt", "Stop", show=True, priority=True),
        # K3: swallow Textual's default help_quit so Ctrl+C does not exit.
        Binding("ctrl+c", "swallow_ctrl_c", show=False, priority=True),
        Binding("ctrl+q", "quit_app", "Quit", show=True),
        # Also allow Ctrl+Enter as send (same as Enter).
        Binding("ctrl+enter", "submit_or_stop", "Send", show=True, priority=True),
    ]

    def __init__(self, history: list, context: dict, *, model_name: str = "") -> None:
        super().__init__()
        self.history = history
        self.context = context
        self._model_name = model_name
        self._busy = False
        self._worker_lock = threading.Lock()
        self._pick_ids: list[str] = []
        self._pick_callback: Callable[[str | None], None] | None = None
        self._picking = False
        self._exit_when_idle = False
        self._live_turn = False

    def compose(self) -> ComposeResult:
        yield Label("", id="usage-bar")
        with VerticalScroll(id="chat-pane"):
            yield Vertical(id="chat-stream")
        with Vertical(id="footer-stack"):
            with Horizontal(id="meta-bar"):
                yield MetaChip("", id="meta-model", chip="model")
                yield MetaChip("", id="meta-mode", chip="mode")
                yield Static("✅ Ready", id="meta-status")
            with Vertical(id="pick-panel"):
                yield Label("", id="pick-title")
                yield OptionList(id="pick-list")
                yield Label("↑↓ move · Enter confirm · Esc close", id="pick-hint")
            with Horizontal(id="composer-row"):
                yield ComposerTextArea(
                    "",
                    id="user-input",
                    soft_wrap=True,
                    show_line_numbers=False,
                    compact=True,
                    tab_behavior="indent",
                    placeholder=_COMPOSER_PLACEHOLDER,
                )
                yield Button("发送", id="send-stop-btn", variant="primary")

    def on_mount(self) -> None:
        set_tui_active(True)
        BRIDGE.bind(self)
        chat = self.query_one("#chat-pane", VerticalScroll)
        chat.border_title = "Chat"
        self.close_inline_picker(notify=False)
        self.refresh_usage_bar()
        self.refresh_meta_bar()
        self._sync_send_stop_button()
        self.hydrate_history()
        self.set_interval(30.0, self.refresh_usage_bar)
        self._focus_composer()

    def on_unmount(self) -> None:
        begin_tui_shutdown()
        request_cancel()
        # Brief wait so worker can notice cancel before console sink opens.
        got = self._worker_lock.acquire(timeout=2.0)
        if got:
            self._worker_lock.release()
        BRIDGE.unbind()
        set_tui_active(False)

    def _composer(self) -> ComposerTextArea:
        return self.query_one("#user-input", ComposerTextArea)

    def _focus_composer(self) -> None:
        try:
            self._composer().focus()
        except Exception:
            pass

    def _get_composer_text(self) -> str:
        try:
            return self._composer().text
        except Exception:
            return ""

    def _set_composer_text(self, text: str) -> None:
        try:
            self._composer().text = text
        except Exception:
            pass

    def _clear_composer(self) -> None:
        self._set_composer_text("")

    # --- Usage + meta ---

    def refresh_usage_bar(self) -> None:
        from harness.ui.tui.usage_bar import format_usage_bar

        try:
            self.query_one("#usage-bar", Label).update(format_usage_bar())
        except Exception:
            pass

    def refresh_meta_bar(self) -> None:
        from harness.models import model_label
        from harness.modes import get_mode

        self._model_name = model_label()
        mode = get_mode()
        try:
            self.query_one("#meta-model", MetaChip).update(f"🤖 {self._model_name}")
            self.query_one("#meta-mode", MetaChip).update(f"🧭 {mode}")
        except Exception:
            pass

    def refresh_model_header(self) -> None:
        self.refresh_meta_bar()
        self.refresh_usage_bar()

    def tui_set_status(self, text: str) -> None:
        raw = (text or "").strip()
        if not raw:
            return
        low = raw.lower()
        if "run" in low or "think" in low or "stop" in low or "work" in low:
            icon = "⚡"
        elif "interrupt" in low or "error" in low or "roll" in low:
            icon = "⚠"
        else:
            icon = "✅"
        try:
            self.query_one("#meta-status", Static).update(f"{icon} {raw}")
        except Exception:
            pass

    def _sync_send_stop_button(self) -> None:
        try:
            btn = self.query_one("#send-stop-btn", Button)
        except Exception:
            return
        if self._busy:
            btn.label = "停止"
            btn.variant = "error"
        else:
            btn.label = "发送"
            btn.variant = "primary"

    def tui_set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        self._sync_send_stop_button()
        # Keep composer enabled so user can edit while running / after stop prefill.
        if self._busy:
            self.tui_set_status("Running… (Esc / Stop)")
        else:
            if not self._exit_when_idle:
                self.tui_set_status("Ready")
            self.refresh_usage_bar()
            self.refresh_meta_bar()
            if not self._picking:
                self._focus_composer()

    def action_pick_model(self) -> None:
        if self._busy:
            return
        from harness.ui.tui.commands import _handle_model

        _handle_model(self, "/model")

    def action_pick_mode(self) -> None:
        if self._busy:
            return
        from harness.ui.tui.commands import _handle_mode

        _handle_mode(self, "/mode")

    # --- Chat stream ---

    def _chat_stream(self) -> Vertical:
        return self.query_one("#chat-stream", Vertical)

    def _scroll_chat_end(self) -> None:
        try:
            self.query_one("#chat-pane", VerticalScroll).scroll_end(animate=False)
        except Exception:
            pass

    def chat_append(self, kind: str, text: str, *, live: bool | None = None) -> None:
        body = (text or "").rstrip()
        if not body:
            return
        use_live = self._live_turn if live is None else live
        extra = f" {_TURN_LIVE}" if use_live else ""
        stream = self._chat_stream()
        if kind == "assistant":
            stream.mount(Markdown(body, classes=f"bubble-assistant{extra}"))
        elif kind == "user":
            stream.mount(Static(f"🧑 {body}", classes=f"bubble-user{extra}", markup=False))
        elif kind == "system":
            stream.mount(Static(f"📎 {body}", classes=f"bubble-system{extra}", markup=False))
        else:
            stream.mount(Static(body, classes=f"bubble-step{extra}", markup=False))
        self._scroll_chat_end()

    def tui_trim_turn_bubbles(self) -> None:
        """U1: remove widgets tagged for the in-flight turn."""
        stream = self._chat_stream()
        for child in list(stream.children):
            try:
                if _TURN_LIVE in child.classes:
                    child.remove()
            except Exception:
                pass
        self._live_turn = False

    def tui_seal_turn_bubbles(self) -> None:
        """Keep bubbles but drop live tag so a later interrupt won't tear them."""
        stream = self._chat_stream()
        for child in list(stream.children):
            try:
                if _TURN_LIVE in child.classes:
                    child.remove_class(_TURN_LIVE)
            except Exception:
                pass
        self._live_turn = False

    def mount_welcome(self) -> None:
        from textual.containers import Horizontal, Vertical

        from harness.ui.tui.welcome_panel import build_welcome_parts, gradient_rule_markup

        wide = self.size.width >= 80
        parts = build_welcome_parts(wide=wide)
        stream = self._chat_stream()

        brand_widgets: list = []
        if parts.wide:
            brand = Horizontal(classes="welcome-brand")
            stream.mount(brand)
            face = Static(parts.smiley, classes="welcome-smiley", markup=False)
            titles = Vertical(classes="welcome-titles")
            title = Static(parts.hello_title, classes="welcome-hello", markup=False)
            tag = Static(parts.tagline, classes="welcome-tagline", markup=False)
            brand.mount(face)
            brand.mount(titles)
            titles.mount(title)
            titles.mount(tag)
            brand_widgets = [face, title, tag]
        else:
            narrow = Static(parts.narrow, classes="welcome-narrow", markup=False)
            stream.mount(narrow)
            brand_widgets = [narrow]

        card = Vertical(classes="welcome-quote-card")
        stream.mount(card)
        q_label = Static(parts.quote_label, classes="welcome-quote-label", markup=False)
        q_body = Static(parts.quote_body, classes="welcome-quote-body", markup=False)
        card.mount(q_label)
        card.mount(q_body)
        quote_widgets = [card, q_label, q_body]
        if parts.quote_source:
            q_src = Static(parts.quote_source, classes="welcome-quote-source", markup=False)
            card.mount(q_src)
            quote_widgets.append(q_src)

        rule_width = min(56, max(24, self.size.width - 6))
        rule = Static(gradient_rule_markup(rule_width), classes="welcome-rule", markup=True)
        stream.mount(rule)
        self._play_welcome_entrance(brand_widgets, quote_widgets, rule)

    def _play_welcome_entrance(
        self,
        brand_widgets: list,
        quote_widgets: list,
        rule: Static,
    ) -> None:
        targets = [*brand_widgets, *quote_widgets, rule]
        for widget in targets:
            try:
                widget.styles.opacity = 0.0
            except Exception:
                return

        def _fade(widget: Static, delay: float) -> None:
            def _run() -> None:
                try:
                    widget.styles.animate("opacity", value=1.0, duration=0.12)
                except Exception:
                    try:
                        widget.styles.opacity = 1.0
                    except Exception:
                        pass

            self.set_timer(delay, _run)

        for i, w in enumerate(brand_widgets):
            _fade(w, 0.02 + i * 0.06)
        brand_end = 0.02 + max(len(brand_widgets), 1) * 0.06
        for i, w in enumerate(quote_widgets):
            _fade(w, brand_end + 0.05 + i * 0.04)
        quote_end = brand_end + 0.05 + max(len(quote_widgets), 1) * 0.04
        _fade(rule, quote_end + 0.05)

    def hydrate_history(self) -> None:
        from harness.ui.tui.chat_history import iter_history_events

        # Cap widgets so a huge session cannot freeze / crash Textual on mount.
        _MAX_HYDRATE_EVENTS = 400

        stream = self._chat_stream()
        for child in list(stream.children):
            child.remove()
        try:
            self.mount_welcome()
        except Exception as exc:
            stream.mount(
                Static(
                    f"(welcome failed: {type(exc).__name__}: {exc})",
                    classes="bubble-system",
                    markup=False,
                )
            )
        try:
            events = list(iter_history_events(self.history))
        except Exception as exc:
            stream.mount(
                Static(
                    f"(history hydrate failed: {type(exc).__name__}: {exc})",
                    classes="bubble-system",
                    markup=False,
                )
            )
            return
        if not events:
            stream.mount(
                Static(
                    "No messages yet — type below to start.",
                    classes="bubble-system",
                    markup=False,
                )
            )
            return
        omitted = 0
        if len(events) > _MAX_HYDRATE_EVENTS:
            omitted = len(events) - _MAX_HYDRATE_EVENTS
            events = events[-_MAX_HYDRATE_EVENTS:]
            stream.mount(
                Static(
                    f"(showing last {_MAX_HYDRATE_EVENTS} of "
                    f"{_MAX_HYDRATE_EVENTS + omitted} history items)",
                    classes="bubble-system",
                    markup=False,
                )
            )
        for kind, text in events:
            try:
                self.chat_append(kind, text, live=False)
            except Exception:
                continue

    def reload_session_view(self) -> None:
        """Re-hydrate Chat after /resume or /clear mutates history/session."""
        self._live_turn = False
        self.hydrate_history()
        self.refresh_usage_bar()
        self.refresh_meta_bar()

    # --- Bridge targets ---

    def tui_reset_turn(self, user_query: str = "", model: str = "") -> None:
        self.close_inline_picker(notify=False)
        self.tui_seal_turn_bubbles()
        self._live_turn = True
        if model:
            self._model_name = model
            self.refresh_meta_bar()
        if user_query.strip():
            self.chat_append("user", user_query.strip(), live=True)
        self.tui_set_status("Running… (Esc / Stop)")

    def tui_append_step(self, line: str) -> None:
        chunk = (line or "").rstrip("\n")
        if not chunk:
            return
        for part in chunk.splitlines():
            if part.strip():
                self.chat_append("step", part)

    def tui_set_answer(self, text: str) -> None:
        self.chat_append("assistant", text)

    def tui_append_assistant(self, text: str) -> None:
        self.tui_set_answer(text)

    # --- Inline picker ---

    def open_inline_picker(
        self,
        title: str,
        labels: list[str],
        item_ids: list[str],
        *,
        initial_index: int = 0,
        on_pick: Callable[[str | None], None] | None = None,
    ) -> None:
        if len(labels) != len(item_ids):
            raise ValueError("labels and item_ids must be the same length")
        self._pick_ids = list(item_ids)
        self._pick_callback = on_pick
        self._picking = True

        panel = self.query_one("#pick-panel", Vertical)
        panel.display = True
        self.query_one("#pick-title", Label).update(title)

        ol = self.query_one("#pick-list", OptionList)
        ol.clear_options()
        for label, item_id in zip(labels, item_ids):
            ol.add_option(Option(label, id=item_id))
        if item_ids:
            ol.highlighted = max(0, min(initial_index, len(item_ids) - 1))
        ol.focus()
        self.tui_set_status(f"{title} — ↑↓ Enter · Esc")

    def close_inline_picker(self, *, notify: bool = True, selected: str | None = None) -> None:
        was = self._picking
        cb = self._pick_callback
        self._picking = False
        self._pick_callback = None
        self._pick_ids = []
        try:
            panel = self.query_one("#pick-panel", Vertical)
            panel.display = False
            ol = self.query_one("#pick-list", OptionList)
            ol.clear_options()
        except Exception:
            pass
        if was and notify and cb is not None:
            cb(selected)
        self._focus_composer()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if not self._picking or event.option_list.id != "pick-list":
            return
        event.stop()
        option_id = event.option.id
        if option_id is None:
            idx = event.option_index
            picked = self._pick_ids[idx] if 0 <= idx < len(self._pick_ids) else None
        else:
            picked = str(option_id)
        self.close_inline_picker(notify=True, selected=picked)

    # --- Send / Stop / Quit ---

    def action_quit_app(self) -> None:
        """X1: cancel in-flight turn before leaving so output cannot leak to terminal."""
        begin_tui_shutdown()
        if self._busy:
            request_cancel()
            self._exit_when_idle = True
            self.tui_set_status("Stopping before exit…")
            return
        self.exit()

    def action_swallow_ctrl_c(self) -> None:
        """K3: do not quit / interrupt on Ctrl+C — tip for terminal copy."""
        self.tui_set_status(
            "Copy: select or Ctrl+Shift+C · Stop: Esc · Quit: Ctrl+Q"
        )

    def action_submit_or_stop(self) -> None:
        """Enter / Ctrl+Enter — send when idle, stop when busy."""
        if self._busy:
            self.action_interrupt()
            return
        self._submit_composer()

    def action_interrupt(self) -> None:
        if self._picking:
            self.close_inline_picker(notify=True, selected=None)
            self.tui_set_status("Picker closed")
            return
        if self._busy:
            request_cancel()
            self.tui_set_status("Stopping…")
            return
        if self._get_composer_text().strip():
            self._clear_composer()
        else:
            self.tui_set_status("Press Ctrl+Q to quit")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "send-stop-btn":
            return
        if self._busy:
            self.action_interrupt()
        else:
            self._submit_composer()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """H1: grow composer height with line count (3–8 rows)."""
        if event.text_area.id != "user-input":
            return
        try:
            lines = max(1, event.text_area.document.line_count)
        except Exception:
            text = event.text_area.text or ""
            lines = max(1, text.count("\n") + 1)
        height = max(3, min(8, lines + (1 if lines < 8 else 0)))
        try:
            event.text_area.styles.height = height
        except Exception:
            pass

    def _submit_composer(self) -> None:
        query = (self._get_composer_text() or "").strip()
        if not query:
            return
        if self._busy:
            return
        if self._picking:
            self.close_inline_picker(notify=False)
        self._clear_composer()
        try:
            self._composer().styles.height = 3
        except Exception:
            pass
        from harness.ui.tui.commands import dispatch_slash

        if dispatch_slash(self, query):
            return
        self._run_turn(query)

    @work(thread=True, exclusive=True, group="agent")
    def _run_turn(self, query: str) -> None:
        if not self._worker_lock.acquire(blocking=False):
            BRIDGE.push_warn("Another turn is still running")
            return
        try:
            from harness.ui.tui.session import run_agent_turn

            result = run_agent_turn(self.history, self.context, query)
            self.context = result.get("context") or self.context
            redo = result.get("redo_query")
            if redo and isinstance(redo, str) and redo.strip():

                def _prefill() -> None:
                    try:
                        self._set_composer_text(redo)
                        lines = max(1, redo.count("\n") + 1)
                        self._composer().styles.height = max(3, min(8, lines + 1))
                        self._focus_composer()
                    except Exception:
                        pass

                self.call_from_thread(_prefill)
        except Exception as exc:
            BRIDGE.trim_turn_bubbles()
            BRIDGE.push_status(f"Turn failed: {exc}")
            BRIDGE.set_busy(False)
        finally:
            try:
                self.call_from_thread(self.refresh_usage_bar)
            except Exception:
                pass
            self._worker_lock.release()
            if self._exit_when_idle:
                try:
                    self.call_from_thread(self.exit)
                except Exception:
                    pass

    @work(thread=True, exclusive=True, group="agent")
    def _run_rag_command(self, query: str) -> None:
        """Run potentially expensive /rag commands without freezing Textual."""
        if not self._worker_lock.acquire(blocking=False):
            BRIDGE.push_warn("Another turn is still running")
            return
        from harness.models import get_model, model_label

        BRIDGE.reset_turn(user_query=query, model=model_label(get_model()))
        BRIDGE.set_busy(True)
        BRIDGE.push_status("Running RAG command…")
        try:
            from harness.rag.commands import run_rag_cli_command

            result = run_rag_cli_command(query)
            BRIDGE.push_final(result)
            BRIDGE.seal_turn_bubbles()
            BRIDGE.push_status("Ready")
        except Exception as exc:
            BRIDGE.push_warn(f"RAG command failed: {type(exc).__name__}: {exc}")
        finally:
            BRIDGE.set_busy(False)
            self._worker_lock.release()
