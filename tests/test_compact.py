"""Tests for compact: safe input budget + prompt-too-long detection."""

from __future__ import annotations

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from harness.agent.compact import (
    COMPACT_TAIL_COUNT,
    _safe_input_budget,
    _structured_summary_instruction,
    compact_history,
    micro_compact,
    summarize_history,
)
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

    def test_structured_summary_prompt_sections(self) -> None:
        text = _structured_summary_instruction()
        for heading in (
            "## Goal",
            "## User Constraints",
            "## Changed Files",
            "## Key Findings",
            "## Remaining Work",
            "## Do NOT Forget",
        ):
            self.assertIn(heading, text)


class TestCompactHistoryTail(unittest.TestCase):
    def test_compact_history_keeps_recent_tail(self) -> None:
        import harness.agent.compact as compact

        messages = [{"role": "user", "content": f"msg-{index}"} for index in range(12)]
        messages.append({"role": "assistant", "content": "latest assistant"})
        messages.append({"role": "user", "content": "latest user"})

        with unittest.mock.patch.object(compact, "write_transcript", return_value=Path("t.jsonl")):
            with unittest.mock.patch.object(compact, "summarize_history", return_value="SUMMARY"):
                with unittest.mock.patch(
                    "harness.project.session_store.record_compact_boundary"
                ):
                    result = compact_history(messages)

        self.assertEqual(result[0]["content"], "[Compacted]\n\nSUMMARY")
        self.assertEqual(len(result), 1 + COMPACT_TAIL_COUNT)
        self.assertEqual(result[-1]["content"], "latest user")
        self.assertEqual(result[-2]["content"], "latest assistant")


class TestMicroCompactPersist(unittest.TestCase):
    def test_micro_compact_persists_instead_of_hard_delete(self) -> None:
        import harness.agent.compact as compact

        long_text = "x" * 500
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tool-old", "content": long_text},
                    {"type": "tool_result", "tool_use_id": "tool-mid", "content": long_text},
                    {"type": "tool_result", "tool_use_id": "tool-new", "content": long_text},
                    {"type": "tool_result", "tool_use_id": "tool-latest", "content": long_text},
                ],
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            tool_dir = Path(tmp) / "tool_results"
            with unittest.mock.patch.object(compact, "TOOL_RESULTS_DIR", tool_dir):
                result = micro_compact(messages)

            old_block = result[0]["content"][0]
            latest_block = result[0]["content"][-1]
            self.assertIn("<persisted-output compacted>", old_block["content"])
            self.assertIn("tool-old.txt", old_block["content"])
            self.assertEqual(latest_block["content"], long_text)
            self.assertTrue((tool_dir / "tool-old.txt").exists())
            self.assertFalse((tool_dir / "tool-latest.txt").exists())


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


if __name__ == "__main__":
    unittest.main()
