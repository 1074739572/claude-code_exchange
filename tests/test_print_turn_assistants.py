"""Regression: final assistant text must still print after compact rewrites history."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from harness.cli import print_turn_assistants


class TestPrintTurnAssistants(unittest.TestCase):
    def test_stale_turn_start_after_compact_still_prints(self) -> None:
        """Pre-compact turn_start may point past the compacted list length."""
        messages = [
            {"role": "user", "content": "[Compacted]\n\nOld summary."},
            {
                "role": "user",
                "content": (
                    "[Current user request]\n"
                    "This is the latest user instruction.\n\n"
                    "阿里百联图文模板推荐步骤"
                ),
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "..."},
                    {"type": "text", "text": "## 推荐五步流程\n\n第一步：选择模板"},
                ],
            },
        ]
        printed: list[str] = []
        with patch("harness.console.terminal_print", side_effect=printed.append):
            # Stale index from before compact (would have been len(history)>=50).
            print_turn_assistants(messages, turn_start=48)

        self.assertEqual(printed, ["## 推荐五步流程\n\n第一步：选择模板"])

    def test_skips_tool_rounds_when_printing(self) -> None:
        messages = [
            {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "will search"},
                    {"type": "tool_use", "id": "1", "name": "bash", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "1", "content": "ok"}],
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "final answer"}],
            },
        ]
        printed: list[str] = []
        with patch("harness.console.terminal_print", side_effect=printed.append):
            print_turn_assistants(messages, turn_start=0)

        self.assertEqual(printed, ["final answer"])


if __name__ == "__main__":
    unittest.main()
