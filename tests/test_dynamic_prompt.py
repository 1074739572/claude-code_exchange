"""Tests for dynamic session context assembly."""

from __future__ import annotations

import unittest
import unittest.mock

from harness.prompts.dynamic import build_session_context, default_time_granularity


class TestDynamicPrompt(unittest.TestCase):
    def test_default_time_granularity_is_minute(self) -> None:
        with unittest.mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(default_time_granularity(), "minute")

    def test_time_granularity_env_seconds(self) -> None:
        with unittest.mock.patch.dict("os.environ", {"HARNESS_TIME_GRANULARITY": "seconds"}):
            self.assertEqual(default_time_granularity(), "seconds")

    def test_latest_user_query_includes_workdir(self) -> None:
        text = build_session_context({"latest_user_query": "写实施方案"})
        self.assertIn("写实施方案", text)
        self.assertIn("harness/", text)
        self.assertNotIn("src/harness/", text.split("there is no")[0])


if __name__ == "__main__":
    unittest.main()
