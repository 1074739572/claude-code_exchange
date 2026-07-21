"""Tests for daily quotes + welcome panel helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock


class DailyQuoteTests(unittest.TestCase):
    def test_same_day_reuses_quote(self):
        from harness.ui.tui import quotes as q

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daily_quotes.json"
            with mock.patch.object(q, "QUOTES_PATH", path), mock.patch.object(
                q, "quotes_path", return_value=path
            ):
                store = {
                    "queue": [
                        {"hitokoto": "first", "from": "a", "uuid": "1"},
                        {"hitokoto": "second", "from": "b", "uuid": "2"},
                    ],
                    "today": None,
                }
                path.write_text(json.dumps(store), encoding="utf-8")
                day = date(2026, 7, 21)
                with mock.patch.object(q, "maybe_refill_async"):
                    a = q.get_daily_quote(day=day)
                    b = q.get_daily_quote(day=day)
                self.assertEqual(a, b)
                self.assertIn("first", a)
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(len(data["queue"]), 1)
                self.assertEqual(data["today"]["date"], "2026-07-21")

    def test_new_day_pops_next(self):
        from harness.ui.tui import quotes as q

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daily_quotes.json"
            with mock.patch.object(q, "QUOTES_PATH", path), mock.patch.object(
                q, "quotes_path", return_value=path
            ):
                path.write_text(
                    json.dumps(
                        {
                            "queue": [
                                {"hitokoto": "day1", "from": "a", "uuid": "1"},
                                {"hitokoto": "day2", "from": "b", "uuid": "2"},
                            ],
                            "today": {
                                "date": "2026-07-20",
                                "hitokoto": "old",
                                "from": "x",
                                "uuid": "",
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                with mock.patch.object(q, "maybe_refill_async"):
                    text = q.get_daily_quote(day=date(2026, 7, 21))
                self.assertIn("day1", text)
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(data["today"]["hitokoto"], "day1")
                self.assertEqual(len(data["queue"]), 1)

    def test_fallback_when_empty(self):
        from harness.ui.tui import quotes as q

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daily_quotes.json"
            with mock.patch.object(q, "QUOTES_PATH", path), mock.patch.object(
                q, "quotes_path", return_value=path
            ):
                path.write_text(json.dumps({"queue": [], "today": None}), encoding="utf-8")
                with mock.patch.object(q, "maybe_refill_async"):
                    text = q.get_daily_quote(day=date(2026, 1, 1))
                self.assertTrue(text.strip())

    def test_refill_uses_fetch(self):
        from harness.ui.tui import quotes as q

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daily_quotes.json"
            with mock.patch.object(q, "QUOTES_PATH", path), mock.patch.object(
                q, "quotes_path", return_value=path
            ):
                path.write_text(json.dumps({"queue": [], "today": None}), encoding="utf-8")
                items = [
                    {"hitokoto": f"q{i}", "from": "api", "uuid": str(i)} for i in range(8)
                ]
                with mock.patch.object(q, "fetch_hitokoto", side_effect=items):
                    with mock.patch.object(q.time, "sleep", return_value=None):
                        result = q.refill_queue(target=5, min_keep=3)
                self.assertTrue(result["ok"])
                self.assertGreaterEqual(result["queue_len"], 5)


class WelcomePanelTests(unittest.TestCase):
    def test_narrow_brand(self):
        from harness.ui.banner import TAGLINE
        from harness.ui.tui.welcome_panel import build_welcome_parts

        with mock.patch(
            "harness.ui.tui.welcome_panel.get_daily_quote_item",
            return_value={"hitokoto": "go", "from": "x", "uuid": ""},
        ), mock.patch("harness.ui.tui.welcome_panel.maybe_refill_async"):
            parts = build_welcome_parts(wide=False)
        self.assertIn("HELLO", parts.narrow)
        self.assertIn(TAGLINE, parts.narrow)

    def test_wide_slim_brand(self):
        from harness.ui.banner import TAGLINE
        from harness.ui.tui.welcome_panel import build_welcome_parts

        with mock.patch(
            "harness.ui.tui.welcome_panel.get_daily_quote_item",
            return_value={"hitokoto": "go", "from": "lab", "uuid": ""},
        ), mock.patch("harness.ui.tui.welcome_panel.maybe_refill_async"):
            parts = build_welcome_parts(wide=True)
        self.assertTrue(parts.wide)
        self.assertIn("╭", parts.smiley)
        self.assertEqual(parts.hello_title, "HELLO")
        self.assertEqual(parts.tagline, TAGLINE)
        self.assertNotIn("██████", parts.smiley)

    def test_quote_card_and_gradient(self):
        from harness.ui.tui.welcome_panel import (
            format_quote_card,
            gradient_rule_markup,
            build_welcome_parts,
        )

        label, body, src = format_quote_card("keep going", "lab")
        self.assertEqual(label, "TODAY")
        self.assertIn("keep going", body)
        self.assertIn("lab", src)
        rule = gradient_rule_markup(24)
        self.assertIn("#E6B84D", rule)
        self.assertIn("#7FDBFF", rule)
        with mock.patch(
            "harness.ui.tui.welcome_panel.get_daily_quote_item",
            return_value={"hitokoto": "keep going", "from": "lab", "uuid": ""},
        ), mock.patch("harness.ui.tui.welcome_panel.maybe_refill_async"):
            parts = build_welcome_parts(wide=True)
        blob = f"{parts.quote_label}{parts.quote_body}{parts.quote_source}"
        self.assertNotIn("Workspace", blob)
        self.assertNotIn("── 会话", blob)


if __name__ == "__main__":
    unittest.main()
