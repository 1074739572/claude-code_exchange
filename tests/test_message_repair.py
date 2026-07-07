"""Tests for message history repair."""

from __future__ import annotations

import unittest

from harness.messages.repair import (
    finalize_cancelled_tool_round,
    repair_tool_pairing,
    strip_trailing_incomplete_tool_turns,
)


class TestMessageRepair(unittest.TestCase):
    def test_strip_trailing_orphan_tool_use(self) -> None:
        messages = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "bash", "input": {}},
                ],
            },
        ]
        removed = strip_trailing_incomplete_tool_turns(messages)
        self.assertEqual(removed, 1)
        self.assertEqual(len(messages), 1)

    def test_repair_inserts_missing_tool_results(self) -> None:
        messages = [
            {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "bash", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2", "content": "x"}]},
        ]
        _, fixes = repair_tool_pairing(messages)
        self.assertGreaterEqual(fixes, 1)
        self.assertEqual(len(messages), 0)

    def test_finalize_cancelled_tool_round(self) -> None:
        messages = [
            {"role": "user", "content": "run"},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "a", "name": "bash", "input": {"command": "echo 1"}},
                    {"type": "tool_use", "id": "b", "name": "bash", "input": {"command": "echo 2"}},
                ],
            },
        ]
        assistant = messages[-1]["content"]
        partial = [
            {"type": "tool_result", "tool_use_id": "a", "content": "1"},
        ]
        finalize_cancelled_tool_round(messages, assistant, partial)
        self.assertEqual(messages[-1]["role"], "user")
        blocks = messages[-1]["content"]
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[1]["tool_use_id"], "b")
        self.assertIn("Interrupted", blocks[1]["content"])


if __name__ == "__main__":
    unittest.main()
