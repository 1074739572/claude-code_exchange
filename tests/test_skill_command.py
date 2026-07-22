"""Tests for manual /skill injection."""

from __future__ import annotations

import unittest
from unittest import mock


class SkillInjectTests(unittest.TestCase):
    def test_inject_skill_appends_marked_user_message(self) -> None:
        from harness.skills_loader import (
            SKILL_LOADED_PREFIX,
            inject_skill,
            skill_loaded_notice,
        )

        messages: list = []
        with mock.patch(
            "harness.skills_loader.SKILL_REGISTRY",
            {
                "demo": {
                    "name": "demo",
                    "description": "Demo skill",
                    "content": "---\nname: demo\n---\nDo the demo.",
                }
            },
        ):
            with mock.patch("harness.skills_loader.scan_skills"):
                with mock.patch(
                    "harness.project.resume.checkpoint_history"
                ) as cp:
                    ok, note = inject_skill("demo", messages, checkpoint=True)
        self.assertTrue(ok)
        self.assertEqual(note, skill_loaded_notice("demo"))
        self.assertEqual(len(messages), 1)
        self.assertTrue(messages[0]["content"].startswith(f"{SKILL_LOADED_PREFIX} demo]"))
        self.assertIn("Do the demo.", messages[0]["content"])
        cp.assert_called_once_with(messages)

    def test_inject_unknown_skill(self) -> None:
        from harness.skills_loader import inject_skill

        messages: list = []
        with mock.patch("harness.skills_loader.SKILL_REGISTRY", {}):
            with mock.patch("harness.skills_loader.scan_skills"):
                ok, note = inject_skill("nope", messages, checkpoint=False)
        self.assertFalse(ok)
        self.assertIn("not found", note.lower())
        self.assertEqual(messages, [])

    def test_run_skill_list_without_messages(self) -> None:
        from harness.skills_loader import run_skill_command

        with mock.patch(
            "harness.skills_loader.format_skill_command_status",
            return_value="Skills\n  - a",
        ):
            self.assertIn("Skills", run_skill_command(""))

    def test_undo_skips_skill_injection(self) -> None:
        from harness.project.session_undo import is_user_turn

        self.assertFalse(
            is_user_turn(
                {
                    "role": "user",
                    "content": "[Skill loaded: demo]\nbody",
                }
            )
        )
        self.assertTrue(is_user_turn({"role": "user", "content": "real question"}))

    def test_hydrate_shows_short_notice(self) -> None:
        from harness.ui.tui.chat_history import iter_history_events

        events = list(
            iter_history_events(
                [
                    {
                        "role": "user",
                        "content": "[Skill loaded: grill-me]\n" + ("x" * 500),
                    }
                ]
            )
        )
        self.assertEqual(events, [("system", "已加载 skill: grill-me")])

    def test_tui_dispatch_skill_list_opens_picker(self) -> None:
        from harness.ui.tui.commands import dispatch_slash

        notes: list[str] = []
        opened: dict = {}

        class FakeApp:
            _busy = False
            history: list = []
            context: dict = {}

            def tui_set_status(self, text: str) -> None:
                pass

            def chat_append(self, kind: str, text: str) -> None:
                notes.append(text)

            def open_inline_picker(self, title, labels, item_ids, *, initial_index=0, on_pick=None):
                opened["title"] = title
                opened["ids"] = item_ids

        with mock.patch(
            "harness.skills_loader.format_skill_command_status",
            return_value="Skills\n  - demo",
        ):
            with mock.patch("harness.skills_loader.scan_skills"):
                with mock.patch(
                    "harness.skills_loader.skill_names",
                    return_value=["demo", "other"],
                ):
                    self.assertTrue(dispatch_slash(FakeApp(), "/skill"))
        self.assertTrue(any("Skills" in n or "demo" in n for n in notes))
        self.assertEqual(opened.get("title"), "Select skill")
        self.assertEqual(opened.get("ids"), ["demo", "other"])

    def test_tui_dispatch_skill_injects_short_notice(self) -> None:
        from harness.ui.tui.commands import dispatch_slash

        notes: list[str] = []

        class FakeApp:
            _busy = False
            history: list = []
            context: dict = {}

            def tui_set_status(self, text: str) -> None:
                pass

            def chat_append(self, kind: str, text: str) -> None:
                notes.append(text)

        with mock.patch(
            "harness.skills_loader.inject_skill",
            return_value=(True, "已加载 skill: demo"),
        ) as inj:
            with mock.patch("harness.messages.repair.repair_tool_pairing"):
                with mock.patch(
                    "harness.context.update_context",
                    side_effect=lambda ctx, hist: dict(ctx),
                ):
                    self.assertTrue(dispatch_slash(FakeApp(), "/skill demo"))
                    inj.assert_called_once()
        self.assertEqual(notes, ["已加载 skill: demo"])
        self.assertTrue(all(len(n) < 80 for n in notes))


if __name__ == "__main__":
    unittest.main()
