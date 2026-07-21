"""Smoke tests for Textual TUI (merged chat + usage/meta)."""

from __future__ import annotations

import os
import unittest
from unittest import mock


class PreferTuiTests(unittest.TestCase):
    def test_prefer_tui_default_on(self):
        from harness.ui.tui.mode import prefer_tui

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HARNESS_TUI", None)
            self.assertTrue(prefer_tui())

    def test_prefer_tui_off_via_env(self):
        from harness.ui.tui.mode import prefer_tui

        for raw in ("0", "false", "off", "classic", "NO"):
            with self.subTest(raw=raw):
                with mock.patch.dict(os.environ, {"HARNESS_TUI": raw}):
                    self.assertFalse(prefer_tui())


class ChatHistoryTests(unittest.TestCase):
    def test_iter_history_user_tools_assistant(self):
        from harness.ui.tui.chat_history import iter_history_events

        messages = [
            {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I will read it"},
                    {
                        "type": "tool_use",
                        "id": "1",
                        "name": "read_file",
                        "input": {"path": "a.py"},
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "1", "content": "ok"},
                ],
            },
            {"role": "assistant", "content": "## Done\n\nAll good."},
        ]
        events = list(iter_history_events(messages))
        kinds = [k for k, _ in events]
        self.assertEqual(kinds[0], "user")
        self.assertIn("step", kinds)
        self.assertEqual(kinds[-1], "assistant")
        self.assertTrue(any("read_file" in t for k, t in events if k == "step"))
        self.assertTrue(any("Done" in t for k, t in events if k == "assistant"))


class TuiImportTests(unittest.TestCase):
    def test_import_textual_app(self):
        from harness.ui.tui.app import HarnessApp
        from harness.ui.tui.bridge import BRIDGE, TuiBridge
        from harness.ui.tui.screens import AllowModal
        from harness.ui.tui.usage_bar import format_usage_bar

        self.assertTrue(issubclass(HarnessApp, object))
        self.assertIsInstance(BRIDGE, TuiBridge)
        self.assertTrue(issubclass(AllowModal, object))
        self.assertIn("今日", format_usage_bar())

    def test_renderer_routes_to_bridge_when_tui_active(self):
        from harness.ui.renderer import renderer
        from harness.ui.tui.bridge import BRIDGE
        from harness.ui.tui.mode import set_tui_active

        steps: list[str] = []
        finals: list[str] = []

        class FakeApp:
            def call_from_thread(self, fn, *args):
                fn(*args)

            def tui_append_step(self, line: str) -> None:
                steps.append(line)

            def tui_set_answer(self, text: str) -> None:
                finals.append(text)

            def tui_set_status(self, text: str) -> None:
                pass

            def tui_set_busy(self, busy: bool) -> None:
                pass

            def tui_reset_turn(self, user_query: str = "", model: str = "") -> None:
                pass

            def refresh_usage_bar(self) -> None:
                pass

            def push_screen(self, screen, callback=None):
                if callback:
                    callback(False)

        set_tui_active(True)
        BRIDGE.bind(FakeApp())
        try:
            renderer.tool_start("bash", {"command": "echo hi"})
            renderer.assistant("# Hello\n\nworld")
            self.assertTrue(any("bash" in s for s in steps))
            self.assertTrue(any("Hello" in f for f in finals))
        finally:
            BRIDGE.unbind()
            set_tui_active(False)

    def test_ask_allow_uses_bridge_in_tui(self):
        from harness.ui.permission_prompt import ask_allow
        from harness.ui.tui.bridge import BRIDGE
        from harness.ui.tui.mode import set_tui_active

        class FakeApp:
            def call_from_thread(self, fn, *args):
                fn(*args)

            def push_screen(self, screen, callback=None):
                if callback:
                    callback(True)

        set_tui_active(True)
        BRIDGE.bind(FakeApp())
        try:
            self.assertTrue(ask_allow(detail="rm -rf tmp", title="Allow?"))
        finally:
            BRIDGE.unbind()
            set_tui_active(False)

    def test_slash_model_by_id(self):
        from harness.ui.tui.commands import dispatch_slash

        calls: dict = {"status": "", "meta": 0, "chat": []}

        class FakeApp:
            def chat_append(self, kind: str, text: str) -> None:
                calls["chat"].append((kind, text))

            def tui_set_status(self, text: str) -> None:
                calls["status"] = text

            def refresh_meta_bar(self) -> None:
                calls["meta"] += 1

            def refresh_model_header(self) -> None:
                calls["meta"] += 1

            def exit(self) -> None:
                pass

            def open_inline_picker(self, *a, **k):
                raise AssertionError("by-id should not open picker")

        with mock.patch("harness.models.set_model", return_value="Switched to x") as sm:
            with mock.patch("harness.models.model_label", return_value="x"):
                self.assertTrue(dispatch_slash(FakeApp(), "/model x"))
                sm.assert_called_once_with("x")
        self.assertIn("Switched", calls["status"])
        self.assertGreaterEqual(calls["meta"], 1)

    def test_slash_model_opens_inline_picker(self):
        from harness.ui.tui.commands import dispatch_slash

        opened: dict = {}

        class FakeApp:
            def tui_set_status(self, text: str) -> None:
                pass

            def chat_append(self, kind: str, text: str) -> None:
                pass

            def open_inline_picker(self, title, labels, item_ids, *, initial_index=0, on_pick=None):
                opened["title"] = title
                opened["ids"] = item_ids
                opened["on_pick"] = on_pick

        with mock.patch(
            "harness.ui.model_picker.menu_entries",
            return_value=(["A", "B"], ["a", "b"], 1),
        ):
            self.assertTrue(dispatch_slash(FakeApp(), "/model"))
        self.assertEqual(opened["title"], "Select model")
        self.assertEqual(opened["ids"], ["a", "b"])


class TuiShutdownSinkTests(unittest.TestCase):
    def test_shutdown_swallows_renderer_not_console(self):
        from harness.ui.renderer import renderer
        from harness.ui.tui.mode import begin_tui_shutdown, clear_tui_shutdown, set_tui_active

        set_tui_active(False)
        begin_tui_shutdown()
        try:
            with mock.patch("harness.ui.renderer._console") as console:
                renderer.tool_start("bash", {"command": "echo hi"})
                renderer.assistant("should not print")
                console.print.assert_not_called()
        finally:
            clear_tui_shutdown()

    def test_trim_helpers_exist_on_app(self):
        from harness.ui.tui.app import HarnessApp

        self.assertTrue(hasattr(HarnessApp, "tui_trim_turn_bubbles"))
        self.assertTrue(hasattr(HarnessApp, "tui_seal_turn_bubbles"))
        self.assertTrue(hasattr(HarnessApp, "action_quit_app"))


if __name__ == "__main__":
    unittest.main()
