"""Tests for identical tool-call repeat guard."""

from __future__ import annotations

import unittest

from harness.agent.repeat_guard import RepeatGuard, tool_fingerprint


class TestRepeatGuard(unittest.TestCase):
    def test_fingerprint_stable(self) -> None:
        a = tool_fingerprint("mcp__fetch__fetch", {"url": "https://a.com"})
        b = tool_fingerprint("mcp__fetch__fetch", {"url": "https://a.com"})
        c = tool_fingerprint("mcp__fetch__fetch", {"url": "https://b.com"})
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_blocks_on_third(self) -> None:
        g = RepeatGuard(limit=3)
        args = {"url": "https://proceedings.mlr.press/v235/"}
        self.assertEqual(g.note("mcp__fetch__fetch", args), (1, False))
        self.assertEqual(g.note("mcp__fetch__fetch", args), (2, False))
        self.assertEqual(g.note("mcp__fetch__fetch", args), (3, True))

    def test_reset_on_change(self) -> None:
        g = RepeatGuard(limit=3)
        self.assertEqual(g.note("bash", {"command": "echo 1"}), (1, False))
        self.assertEqual(g.note("bash", {"command": "echo 1"}), (2, False))
        self.assertEqual(g.note("bash", {"command": "echo 2"}), (1, False))


if __name__ == "__main__":
    unittest.main()
