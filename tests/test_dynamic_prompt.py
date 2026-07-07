"""Tests for dynamic session context assembly."""

from __future__ import annotations

import unittest

from harness.prompts.dynamic import build_session_context


class TestDynamicPrompt(unittest.TestCase):
    def test_latest_user_query_includes_workdir(self) -> None:
        text = build_session_context({"latest_user_query": "写实施方案"})
        self.assertIn("写实施方案", text)
        self.assertIn("harness/", text)
        self.assertNotIn("src/harness/", text.split("there is no")[0])


if __name__ == "__main__":
    unittest.main()
