"""Unit tests for GAIA official scorer + answer extraction."""

from __future__ import annotations

import unittest

from evals.gaia.scorer import extract_final_answer, question_scorer


class TestGaiaScorer(unittest.TestCase):
    def test_number(self) -> None:
        self.assertTrue(question_scorer("41", "41"))
        self.assertTrue(question_scorer("$41", "41"))
        self.assertTrue(question_scorer("41%", "41"))
        self.assertFalse(question_scorer("42", "41"))

    def test_string(self) -> None:
        self.assertTrue(question_scorer("egalitarian", "egalitarian"))
        self.assertTrue(question_scorer("Egalitarian!", "egalitarian"))
        self.assertTrue(question_scorer("sea gull", "seagull"))
        self.assertFalse(question_scorer("hierarchy", "egalitarian"))

    def test_list(self) -> None:
        self.assertTrue(question_scorer("1, 2, 3", "1,2,3"))
        self.assertTrue(question_scorer("a; b", "a,b"))
        self.assertFalse(question_scorer("1, 2", "1,2,3"))

    def test_extract_final_answer(self) -> None:
        text = "I think carefully.\nFINAL ANSWER: egalitarian\n"
        self.assertEqual(extract_final_answer(text), "egalitarian")
        text2 = "Reasoning...\nFinal Answer: 34689"
        self.assertEqual(extract_final_answer(text2), "34689")
        self.assertEqual(extract_final_answer("[Stopped] reached max_rounds=40"), "")

    def test_extract_from_messages_skips_stopped(self) -> None:
        from evals.gaia.scorer import extract_final_answer_from_messages

        messages = [
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "FINAL ANSWER: 41"}],
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "[Stopped] reached max_rounds=40"}
                ],
            },
        ]
        self.assertEqual(extract_final_answer_from_messages(messages), "41")


if __name__ == "__main__":
    unittest.main()
