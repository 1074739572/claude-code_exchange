"""Tests for goal stickiness, permission deny patterns, final-answer emit."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from harness.hooks import _DESTRUCTIVE_RE, _NESTED_AGENT_RE, permission_hook
from harness.prompts.goal_stickiness import (
    augment_if_needed,
    looks_like_correction,
    looks_like_slot_fill,
)
from harness.ui.final_answer import emit_final_assistant
from harness.ui.tui.events import PermissionResponse


class TestGoalStickiness(unittest.TestCase):
    def test_correction_detected(self) -> None:
        self.assertTrue(looks_like_correction("我让你运行vanna 你在干什么？"))
        self.assertTrue(looks_like_correction("那你继续运行啊"))

    def test_slot_fill_model_name(self) -> None:
        self.assertTrue(looks_like_slot_fill("deepseek-v4-flash"))
        self.assertTrue(looks_like_slot_fill("ok"))
        self.assertFalse(looks_like_slot_fill("请帮我重构整个 harness 的权限系统"))

    def test_augment_adds_tail(self) -> None:
        out = augment_if_needed("我让你运行 vanna")
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("[Harness] Stay on the user's Working goal", out)
        self.assertIn("Vanna", out)


class TestPermissionPatterns(unittest.TestCase):
    def test_nested_agent_denied(self) -> None:
        block = {
            "type": "tool_use",
            "name": "bash",
            "input": {
                "command": (
                    'cd D:\\proj && python -c "from harness.cli import run_cli; run_cli()"'
                )
            },
        }
        msg = permission_hook(block)
        self.assertIsNotNone(msg)
        assert msg is not None
        self.assertIn("nested interactive agent", msg)

    def test_start_cmd_denied(self) -> None:
        block = {
            "type": "tool_use",
            "name": "bash",
            "input": {"command": "start cmd /k python main.py"},
        }
        msg = permission_hook(block)
        self.assertIsNotNone(msg)
        assert msg is not None
        self.assertIn("nested", msg.lower())

    def test_rm_substring_in_from_not_destructive(self) -> None:
        # "from" must not trip destructive; real "rm file" should.
        self.assertIsNone(_DESTRUCTIVE_RE.search("python -c 'from harness.cli import x'"))
        self.assertIsNotNone(_DESTRUCTIVE_RE.search("rm foo.txt"))
        self.assertIsNotNone(_NESTED_AGENT_RE.search("python main.py"))

    def test_destructive_command_can_be_edited_inline_before_allow(self) -> None:
        block = {
            "type": "tool_use",
            "name": "bash",
            "input": {"command": "rm old.txt"},
        }
        with patch(
            "harness.hooks.ask_permission",
            return_value=PermissionResponse("p1", "allow", "rm safe.txt"),
        ):
            self.assertIsNone(permission_hook(block))
        self.assertEqual(block["input"]["command"], "rm safe.txt")


class TestEmitFinalAssistant(unittest.TestCase):
    def test_marks_printed_and_calls_terminal(self) -> None:
        messages = [
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "done"}],
            }
        ]
        with patch("harness.ui.final_answer.terminal_print") as mock_print:
            emit_final_assistant(messages, messages[0]["content"])
        mock_print.assert_called_once_with("done")
        self.assertTrue(messages[0].get("_ui_final_printed"))

    def test_print_turn_skips_already_printed(self) -> None:
        from harness.cli import print_turn_assistants

        messages = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "answer"}],
                "_ui_final_printed": True,
            },
        ]
        printed: list[str] = []
        with patch("harness.console.terminal_print", side_effect=printed.append):
            print_turn_assistants(messages, turn_start=0)
        self.assertEqual(printed, [])


if __name__ == "__main__":
    unittest.main()
