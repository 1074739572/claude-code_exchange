"""Tests for compact: safe input budget + prompt-too-long detection."""

from __future__ import annotations

import unittest

from harness.agent.compact import _safe_input_budget, summarize_history
from harness.agent.recovery import is_prompt_too_long_error


class TestSafeInputBudget(unittest.TestCase):
    def test_budget_under_deepseek_limit(self) -> None:
        budget = _safe_input_budget("deepseek-v4-flash")
        # 1M context -> ~250K chars, well above the old 12K floor
        self.assertGreater(budget, 100_000)

    def test_qwen_max_small_context(self) -> None:
        budget = _safe_input_budget("qwen-max")
        # 32K context, 12K reserve -> 20K tokens -> 80K chars
        self.assertGreater(budget, 50_000)
        self.assertLess(budget, 100_000)

    def test_unknown_model_falls_back(self) -> None:
        budget = _safe_input_budget("unknown-model-xyz")
        self.assertGreaterEqual(budget, 12_000)


class TestSummarizeHistoryFallback(unittest.TestCase):
    def test_returns_fallback_on_api_error(self) -> None:
        import harness.agent.compact as compact

        class Boom(Exception):
            pass

        def boom(**kwargs):
            raise Boom("Range of input length should be [1, 30720]")

        with unittest.mock.patch.object(compact, "create_message", side_effect=boom):
            with unittest.mock.patch.object(compact, "get_model", return_value="m1"):
                result = summarize_history([{"role": "user", "content": "hi"}])
        self.assertIn("Compact summary unavailable", result)


class TestPromptTooLong(unittest.TestCase):
    def test_deepseek_range_error_detected(self) -> None:
        exc = Exception(
            "BadRequestError: 400 - Range of input length should be [1, 30720]"
        )
        self.assertTrue(is_prompt_too_long_error(exc))

    def test_anthropic_context_length_detected(self) -> None:
        self.assertTrue(is_prompt_too_long_error(Exception("context_length_exceeded")))
        self.assertTrue(is_prompt_too_long_error(Exception("prompt is too long")))

    def test_unrelated_error_not_matched(self) -> None:
        self.assertFalse(is_prompt_too_long_error(Exception("network timeout")))


import unittest.mock  # noqa: E402

if __name__ == "__main__":
    unittest.main()
